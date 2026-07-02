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
