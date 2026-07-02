import Bar from './Bar'
import { COMPONENT_COLORS } from '../config'
import { qualitative, capitalize } from '../lib/format'

// Detail panel for a clicked safe-route segment. Uses the scores embedded in the
// route response (no extra request). Aggregated component scores only. When a
// segment is on the neutral-lighting fallback we say so plainly rather than
// implying a measured lighting value.
export default function SegmentDetail({ segment, timeOfDay, onClose }) {
  if (!segment) return null

  return (
    <div className="segment-detail">
      <div className="panel-head">
        <span className="panel-title">Segment detail</span>
        <button className="panel-close" onClick={onClose} aria-label="Close segment detail">
          ×
        </button>
      </div>

      <Bar
        label={`Incidents (${timeOfDay})`}
        value={segment.incident_density}
        valueLabel={qualitative(segment.incident_density)}
        color={COMPONENT_COLORS.incidents}
      />

      {segment.has_lighting_data ? (
        <Bar
          label="Lighting"
          value={segment.lighting_score}
          valueLabel={qualitative(segment.lighting_score)}
          color={COMPONENT_COLORS.lighting}
        />
      ) : (
        <p className="fallback-note">Limited lighting data here — treated as neutral.</p>
      )}
    </div>
  )
}
