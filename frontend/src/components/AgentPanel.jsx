import { useState } from 'react'

// Natural-language input for the agent. Submitting calls onAsk(text); the answer
// renders below. A single tool-using assistant — not multiple agents.
export default function AgentPanel({ onAsk, loading, answer, error }) {
  const [text, setText] = useState('')

  const submit = (e) => {
    e.preventDefault()
    const trimmed = text.trim()
    if (trimmed && !loading) onAsk(trimmed)
  }

  return (
    <form className="agent-panel" onSubmit={submit}>
      <span className="control-label">Ask SafeRouteNYC</span>
      <textarea
        className="agent-input"
        rows={2}
        placeholder="e.g. safest way from Times Square to Union Square at 1am"
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) submit(e)
        }}
      />
      <button className="agent-submit" type="submit" disabled={loading || !text.trim()}>
        {loading ? 'Thinking…' : 'Ask'}
      </button>
      {error && <p className="fallback-note">{error}</p>}
      {answer && <p className="agent-answer">{answer}</p>}
    </form>
  )
}
