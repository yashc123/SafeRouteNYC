import { ROUTE_COLORS } from '../config'

// Minimal, unobtrusive legend: teal = safe, gray = fast. Info-only (no pointer
// events, so it never blocks map clicks).
export default function Legend() {
  return (
    <div className="legend">
      <div className="legend-row">
        <span className="legend-swatch" style={{ background: ROUTE_COLORS.safe }} />
        Safe route
      </div>
      <div className="legend-row">
        <span className="legend-swatch" style={{ background: ROUTE_COLORS.fast }} />
        Fast route
      </div>
    </div>
  )
}
