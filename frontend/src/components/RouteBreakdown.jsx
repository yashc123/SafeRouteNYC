import Bar from './Bar'
import { COMPONENT_COLORS } from '../config'
import { qualitative, capitalize } from '../lib/format'

// Route-level "why this route" breakdown for the SAFE route: the aggregated
// components that drive its safety score. Aggregated scores only — never
// individual incidents. Renders nothing until a route exists.
export default function RouteBreakdown({ safe }) {
  const c = safe?.components
  if (!c) return null

  const coveragePct = Math.round((c.lighting_coverage ?? 0) * 100)

  return (
    <div className="breakdown-card">
      <span className="panel-title">Why this route</span>

      <Bar
        label="Incidents"
        value={c.incident_density}
        valueLabel={qualitative(c.incident_density)}
        color={COMPONENT_COLORS.incidents}
      />
      <Bar
        label="Lighting"
        value={c.lighting_score}
        valueLabel={qualitative(c.lighting_score)}
        color={COMPONENT_COLORS.lighting}
      />

      {/* Honest coverage note: don't imply lighting certainty we don't have. */}
      <p className="coverage-note">
        Lighting data on {coveragePct}% of the route; the rest is treated as neutral.
      </p>

      <div className="time-factor">
        <span className="tf-label">Time factor</span>
        <span className="tf-chip">{capitalize(c.time_of_day)}</span>
      </div>
    </div>
  )
}
