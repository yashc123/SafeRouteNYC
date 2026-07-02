// Small display formatters for the route comparison cards.
// Distance is shown in MILES (NYC/US audience; friendlier than km for walking),
// one decimal. Time is whole minutes. Safety is a whole 0-100 integer.

const METERS_PER_MILE = 1609.344

export function formatDuration(minutes) {
  if (minutes == null) return '—'
  return `${Math.round(minutes)} min`
}

export function formatDistanceMiles(meters) {
  if (meters == null) return '—'
  return `${(meters / METERS_PER_MILE).toFixed(1)} mi`
}

export function formatSafety(score) {
  if (score == null) return '—'
  return Math.round(score)
}

// Qualitative label for a 0-1 score, for the calm labeled bars.
export function qualitative(value) {
  if (value == null) return '—'
  if (value >= 0.66) return 'high'
  if (value >= 0.33) return 'moderate'
  return 'low'
}

export function capitalize(text) {
  return text ? text[0].toUpperCase() + text.slice(1) : text
}
