import { useEffect, useState } from 'react'
import SearchField from './SearchField'
import ModeToggle from './ModeToggle'
import {
  SLIDER_DEBOUNCE_MS,
  TIME_OF_DAY_OPTIONS,
  MARKER_COLORS,
  alphaToSlider,
  sliderToAlpha,
} from '../config'

// Compact control card. Mode toggle on top. In Route mode: address search +
// safety-vs-speed slider. Both modes: time-of-day selector (area safety is
// time-dependent too). It only calls the setters passed in; never touches the map.
export default function ControlPanel({
  mode,
  alpha,
  timeOfDay,
  origin,
  destination,
  onModeChange,
  onAlphaChange,
  onTimeChange,
  onOriginSelect,
  onDestinationSelect,
}) {
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
      <ModeToggle mode={mode} onChange={onModeChange} />

      {mode === 'route' && (
        <>
          <section className="control-section">
            <span className="control-label">Route</span>
            <SearchField
              color={MARKER_COLORS.origin}
              placeholder="Start address"
              endpoint={origin}
              onSelect={onOriginSelect}
            />
            <SearchField
              color={MARKER_COLORS.destination}
              placeholder="Destination address"
              endpoint={destination}
              onSelect={onDestinationSelect}
            />
          </section>

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
        </>
      )}

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

      {mode === 'explore' && (
        <p className="explore-hint">Tap anywhere on the map to check that area’s safety.</p>
      )}
    </div>
  )
}
