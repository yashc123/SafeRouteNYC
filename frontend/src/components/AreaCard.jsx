import Bar from './Bar'
import { COMPONENT_COLORS } from '../config'
import { qualitative, capitalize } from '../lib/format'

// Calm, supportive summary label. Someone checking area safety may be anxious, so
// wording is measured — never "dangerous", never alarmist. Honest about limited
// lighting data (most areas have sparse OSM lamp coverage).
function areaLabel(components) {
  const incidents = components.incident_density ?? 0
  const lit = (components.lighting_coverage ?? 0) >= 0.15

  if (!lit) {
    if (incidents < 0.4) return 'Calmer area — limited lighting data'
    if (incidents < 0.7) return 'Mixed activity — limited lighting data'
    return 'Busier area — limited lighting data'
  }
  if (components.lighting_score >= 0.6 && incidents < 0.4) return 'Well lit, low incidents'
  if (incidents >= 0.7) return 'Busier area'
  return 'Mixed'
}

export default function AreaCard({ area, loading, error, timeOfDay, onRouteHere, onClose }) {
  if (!area && !loading && !error) return null

  return (
    <div className="area-card">
      <div className="panel-head">
        <span className="panel-title">Area safety</span>
        <button className="panel-close" onClick={onClose} aria-label="Close area safety">
          ×
        </button>
      </div>

      {loading && <p className="area-loading">Checking this area…</p>}
      {error && !loading && <p className="fallback-note">Couldn’t check this area — try again.</p>}

      {area && !loading && (
        <>
          <div className="area-score">
            <span className="area-score-num">{Math.round(area.area_safety_score)}</span>
            <span className="area-score-max">/ 100</span>
          </div>
          <p className="area-label">{areaLabel(area.components)}</p>

          <Bar
            label="Incidents"
            value={area.components.incident_density}
            valueLabel={qualitative(area.components.incident_density)}
            color={COMPONENT_COLORS.incidents}
          />
          <Bar
            label="Lighting"
            value={area.components.lighting_score}
            valueLabel={qualitative(area.components.lighting_score)}
            color={COMPONENT_COLORS.lighting}
          />

          <p className="coverage-note">
            Lighting data on {Math.round((area.components.lighting_coverage ?? 0) * 100)}% of this
            area; the rest is treated as neutral.
          </p>

          <div className="time-factor">
            <span className="tf-label">Time factor</span>
            <span className="tf-chip">{capitalize(timeOfDay)}</span>
          </div>

          <button className="route-here-btn" onClick={() => onRouteHere(area.snapped)}>
            Route to here →
          </button>
        </>
      )}
    </div>
  )
}
