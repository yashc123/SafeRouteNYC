import { API_URL } from '../config'

// POST /route — origin/destination are {lat, lng}. alpha and timeOfDay are
// optional; when omitted the backend applies its defaults (alpha=3, night).
// Returns the parsed JSON: { time_of_day, safe_alpha, fast{...}, safe{...}, cache }.
export async function postRoute({ origin, destination, alpha, timeOfDay }) {
  const body = { origin, destination }
  if (alpha != null) body.alpha = alpha
  if (timeOfDay != null) body.time_of_day = timeOfDay

  const res = await fetch(`${API_URL}/route`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })

  if (!res.ok) {
    throw await errorFrom(res)
  }

  return res.json()
}

// GET /area-safety — Explore mode. Returns the tapped area's aggregated safety.
export async function fetchAreaSafety({ lat, lng, timeOfDay }) {
  const params = new URLSearchParams({ lat: String(lat), lng: String(lng) })
  if (timeOfDay != null) params.set('time_of_day', timeOfDay)

  const res = await fetch(`${API_URL}/area-safety?${params.toString()}`)
  if (!res.ok) {
    throw await errorFrom(res)
  }
  return res.json()
}

// GET /coverage — is a point within the covered Manhattan street network?
// Fails OPEN (returns in_bounds:true) if the check itself errors, so a coverage
// hiccup never blocks a legitimate click.
export async function checkCoverage({ lat, lng }) {
  try {
    const params = new URLSearchParams({ lat: String(lat), lng: String(lng) })
    const res = await fetch(`${API_URL}/coverage?${params.toString()}`)
    if (!res.ok) return { in_bounds: true }
    return res.json()
  } catch {
    return { in_bounds: true }
  }
}

// POST /agent — natural-language request. Returns { answer, route, area,
// reachable, history }. route/area are the same shapes the map already draws.
export async function postAgent({ message, history }) {
  const res = await fetch(`${API_URL}/agent`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history: history || null }),
  })
  if (!res.ok) {
    throw await errorFrom(res)
  }
  return res.json()
}

// Surface the backend's error detail when present, else a generic message.
async function errorFrom(res) {
  let message = `Request failed (HTTP ${res.status})`
  try {
    const data = await res.json()
    if (data?.detail) {
      message = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    }
  } catch {
    /* non-JSON error body — keep the generic message */
  }
  return new Error(message)
}
