// A single calm labeled bar: label + qualitative value, and a muted track with a
// colored fill proportional to a 0-1 value. Deliberately not alarmist — no red,
// no incident plotting; just an aggregated score.
export default function Bar({ label, value, valueLabel, color }) {
  const pct = Math.round(Math.max(0, Math.min(1, value ?? 0)) * 100)
  return (
    <div className="bar-row">
      <div className="bar-head">
        <span className="bar-label">{label}</span>
        <span className="bar-value">{valueLabel}</span>
      </div>
      <div className="bar-track">
        <div className="bar-fill" style={{ width: `${pct}%`, background: color }} />
      </div>
    </div>
  )
}
