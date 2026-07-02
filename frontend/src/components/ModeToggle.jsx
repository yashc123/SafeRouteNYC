// Quiet two-option pill toggle: Route vs Explore. Same segmented look as the
// time-of-day control (not a loud tab bar).
const MODES = [
  { id: 'route', label: 'Route' },
  { id: 'explore', label: 'Explore' },
]

export default function ModeToggle({ mode, onChange }) {
  return (
    <div className="mode-toggle segmented" role="group" aria-label="Mode">
      {MODES.map((m) => (
        <button
          key={m.id}
          type="button"
          className={`segment ${mode === m.id ? 'active' : ''}`}
          aria-pressed={mode === m.id}
          onClick={() => onChange(m.id)}
        >
          {m.label}
        </button>
      ))}
    </div>
  )
}
