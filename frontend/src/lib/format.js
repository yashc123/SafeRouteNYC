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
