// Single small status/hint pill. Doubles as the required loading + error
// indicator and a one-line hint that keeps the click interaction obvious.
export default function StatusPill({ origin, destination, loading, error }) {
  let text
  let tone = 'info'

  if (error) {
    text = `Route error: ${error}`
    tone = 'error'
  } else if (loading) {
    text = 'Finding routes…'
    tone = 'loading'
  } else if (!origin) {
    text = 'Click the map to set a start point'
  } else if (!destination) {
    text = 'Click to set a destination'
  } else {
    text = 'Click anywhere to start over'
  }

  return <div className={`status-pill status-${tone}`}>{text}</div>
}
