import { useEffect, useState } from 'react'
import {
  SLIDER_DEBOUNCE_MS,
  TIME_OF_DAY_OPTIONS,
  alphaToSlider,
  sliderToAlpha,
} from '../config'

// Compact control card: safety-vs-speed slider + time-of-day selector. It only
// calls the routing setters passed in (onAlphaChange / onTimeChange); it never
// touches the map. Structured so later sub-steps can add more sections here.
export default function ControlPanel({ alpha, timeOfDay, onAlphaChange, onTimeChange }) {
  // Local slider position for smooth dragging; the committed alpha is debounced.
  const [slider, setSlider] = useState(() => alphaToSlider(alpha))

  // Debounce: each move restarts a timer; alpha (and the refetch) only commits
  // once the user pauses for SLIDER_DEBOUNCE_MS.
  useEffect(() => {
    const timer = setTimeout(() => onAlphaChange(sliderToAlpha(slider)), SLIDER_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [slider, onAlphaChange])

  return (
    <div className="control-panel">
      <section className="control-section">
        <label className="control-label" htmlFor="safety-slider">
          Route priority
        </label>
        <input
          id="safety-slider"
          className="safety-slider"
          type="range"
          min="0"
          max="100"
          value={slider}
          onChange={(e) => setSlider(Number(e.target.value))}
        />
        <div className="slider-ends">
          <span>Fastest</span>
          <span>Safest</span>
        </div>
      </section>

      <section className="control-section">
        <span className="control-label">Time of day</span>
        <div className="segmented" role="group" aria-label="Time of day">
          {TIME_OF_DAY_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              className={`segment ${timeOfDay === option ? 'active' : ''}`}
              aria-pressed={timeOfDay === option}
              onClick={() => onTimeChange(option)}
            >
              {option[0].toUpperCase() + option.slice(1)}
            </button>
          ))}
        </div>
      </section>
    </div>
  )
}
