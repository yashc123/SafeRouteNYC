"""SafePath agent — a SINGLE Claude tool-using agent (not multi-agent).

The loop is the standard Anthropic function-calling cycle:
  1. Send the user message + tool definitions to Claude.
  2. If Claude returns tool_use blocks, dispatch each to the REAL engine function
     (agent_tools.dispatch_tool) and send the tool_result back.
  3. Repeat until Claude returns a final text answer.

Grounding: the agent may only state values that came from tool results. This is
enforced two ways — (1) the system prompt forbids inventing any number, and
(2) the tools are the sole source of factual data, and the frontend draws the map
from the tool artifacts (real computed geometry), not from the model's text.
"""

import json
import os
from pathlib import Path

from anthropic import Anthropic
from dotenv import load_dotenv

from agent_tools import TOOLS, dispatch_tool

load_dotenv(Path(__file__).resolve().parent / ".env")

# Sonnet 5: strong tool-use reasoning at good latency/cost for an interactive agent.
MODEL = "claude-sonnet-5"
MAX_STEPS = 8       # safety cap on tool-use round trips
MAX_TOKENS = 1024

SYSTEM_PROMPT = """You are SafePath's assistant. You help people plan safer walking \
routes and check area safety in Manhattan, New York. You are a single assistant that \
uses tools — not a team of agents.

You have tools that call SafePath's REAL routing engine:
- geocode(place_name): resolve a place/address to coordinates.
- get_route(origin, destination, alpha, time_of_day): returns BOTH a safe and a fast route.
- get_area_safety(lat, lng, time_of_day): safety profile of the area around a point.
- get_reachable(lat, lng, alpha, time_of_day, budget_min): area reachable within a walk-time budget.

CRITICAL GROUNDING RULE: Every factual value — coordinates, distances, walk times, \
safety scores, incident or lighting levels, reachable areas — MUST come from a tool \
result. NEVER invent, estimate, or guess a safety score, distance, time, or any number. \
If you have not called a tool to obtain a value, do not state it. If a tool returns an \
error or no result, say so plainly and suggest what the user could try (e.g. a more \
specific address). Do not describe individual crimes — only the aggregated scores the \
tools return.

Workflow: resolve place names to coordinates with geocode before routing or an area \
lookup. Use get_route for A-to-B. alpha is the safety weighting (0-10, higher = safer; \
default 3). time_of_day is day, evening, or night — infer it from the user's wording \
('1am' -> night, 'noon' -> day) and default to night if unclear.

Answer concisely, calmly, and supportively. State the real numbers from the tools \
(e.g. distance in miles from meters, walk time, safety score out of 100) and explain \
the safe-vs-fast tradeoff using those values.

When you attach a qualitative word to a 0-1 component score, use this fixed scale and \
never contradict the number: below 0.33 = low, 0.33 to 0.66 = moderate, above 0.66 = \
high. Mind the direction: a HIGHER incident_density means MORE incidents (worse), while \
a HIGHER lighting_score means better lit (better). So incident_density 0.778 is HIGH \
incident activity, not low. The overall safety_score already accounts for both, so a \
high safety_score can coexist with high incident_density when lighting is strong — \
describe each component by its own value, don't infer it from the overall score."""

_client = None


def agent_available():
    """True if the agent can run (a real Anthropic key is configured)."""
    key = os.getenv("ANTHROPIC_API_KEY")
    return bool(key) and key != "your-anthropic-api-key-here"


def _get_client():
    global _client
    if _client is None:
        _client = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
    return _client


def run_agent(user_message, history=None):
    """Run the tool-use loop. `history` is an optional list of prior {role, content}
    text turns. Returns {answer, artifacts, history}."""
    client = _get_client()
    messages = list(history or []) + [{"role": "user", "content": user_message}]
    artifacts = {}

    for _ in range(MAX_STEPS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            # Record Claude's turn (text + tool_use blocks), then answer each tool call.
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = dispatch_tool(block.name, block.input, artifacts)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    })
            messages.append({"role": "user", "content": tool_results})
            continue

        # Final answer.
        answer = "".join(block.text for block in response.content if block.type == "text").strip()
        new_history = list(history or []) + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": answer},
        ]
        return {"answer": answer, "artifacts": artifacts, "history": new_history}

    return {
        "answer": "Sorry — I couldn't complete that request in a reasonable number of steps.",
        "artifacts": artifacts,
        "history": list(history or []),
    }
