import { ROUTE_COLORS } from '../config'
import { formatDuration, formatDistanceMiles, formatSafety } from '../lib/format'

// Two side-by-side comparison cards (safe + fast). Purely presentational: it reads
// the numbers already in routing state via the `routes` prop, so it re-renders
// live whenever the routes change (slider drag, time change). Renders nothing
// until both routes exist, and disappears again on reset (routes -> null).
function RouteCard({ variant, label, route, recommended }) {
  return (
    <div className={`route-card ${variant} ${recommended ? 'recommended' : ''}`}>
      <div className="card-header">
        <span className="card-dot" style={{ background: ROUTE_COLORS[variant] }} />
        <span className="card-title">{label}</span>
        {recommended && <span className="card-tag">Recommended</span>}
      </div>
      <div className="card-stats">
        <div className="stat">
          <span className="stat-value">{formatDuration(route.duration_min)}</span>
          <span className="stat-label">Time</span>
        </div>
        <div className="stat">
          <span className="stat-value">{formatDistanceMiles(route.distance_m)}</span>
          <span className="stat-label">Distance</span>
        </div>
      </div>
      <div className="card-safety">
        Safety <strong>{formatSafety(route.safety_score)}</strong> / 100
      </div>
    </div>
  )
}

export default function RouteCards({ routes }) {
  if (!routes?.safe || !routes?.fast) return null
  return (
    <div className="route-cards">
      <RouteCard variant="safe" label="Safe route" route={routes.safe} recommended />
      <RouteCard variant="fast" label="Fast route" route={routes.fast} />
    </div>
  )
}
