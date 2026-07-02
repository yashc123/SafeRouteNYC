import { useEffect, useRef, useState } from 'react'
import { searchPlaces } from '../lib/geocode'
import { GEOCODE_DEBOUNCE_MS } from '../config'

const MIN_QUERY = 3

// One address input with a debounced MapTiler autocomplete dropdown. Selecting a
// suggestion calls onSelect({lat, lng}); the parent turns that into origin/dest.
// `endpoint` is the current origin/destination point — we watch it so the field
// clears when that endpoint is changed elsewhere (a map click) or reset.
export default function SearchField({ color, placeholder, endpoint, onSelect }) {
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const [open, setOpen] = useState(false)
  const [status, setStatus] = useState(null) // 'loading' | 'empty' | 'error' | null
  const selectedPointRef = useRef(null) // the point this field's text corresponds to

  // Keep the field in sync with external endpoint changes: if the endpoint no
  // longer matches what we selected (map click set it, or reset cleared it),
  // clear the text so it never shows a stale address.
  useEffect(() => {
    const sel = selectedPointRef.current
    const matches = endpoint && sel && endpoint.lat === sel.lat && endpoint.lng === sel.lng
    if (!matches) {
      selectedPointRef.current = null
      setQuery('')
      setSuggestions([])
      setStatus(null)
      setOpen(false)
    }
  }, [endpoint])

  // Debounced geocoding: fire only after the user pauses; cancel in-flight
  // requests on the next keystroke via AbortController.
  useEffect(() => {
    const q = query.trim()
    if (q.length < MIN_QUERY || q === selectedPointRef.current?.label) {
      setSuggestions([])
      setStatus(null)
      return
    }
    const controller = new AbortController()
    const timer = setTimeout(async () => {
      setStatus('loading')
      setOpen(true)
      try {
        const results = await searchPlaces(q, controller.signal)
        setSuggestions(results)
        setStatus(results.length ? null : 'empty')
      } catch (err) {
        if (err.name !== 'AbortError') {
          setSuggestions([])
          setStatus('error')
        }
      }
    }, GEOCODE_DEBOUNCE_MS)

    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [query])

  const handleSelect = (place) => {
    selectedPointRef.current = { lat: place.lat, lng: place.lng, label: place.label }
    setQuery(place.label)
    setSuggestions([])
    setStatus(null)
    setOpen(false)
    onSelect({ lat: place.lat, lng: place.lng })
  }

  const showDropdown = open && (status !== null || suggestions.length > 0)

  return (
    <div className="search-field">
      <span className="search-dot" style={{ background: color }} />
      <input
        className="search-input"
        type="text"
        value={query}
        placeholder={placeholder}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => (suggestions.length > 0 || status) && setOpen(true)}
        onBlur={() => setOpen(false)}
      />
      {showDropdown && (
        <ul className="search-dropdown">
          {status === 'loading' && <li className="search-note">Searching…</li>}
          {status === 'empty' && <li className="search-note">No matches in this area</li>}
          {status === 'error' && <li className="search-note">Search unavailable</li>}
          {suggestions.map((place) => (
            <li
              key={place.id}
              className="search-option"
              // onMouseDown fires before the input's onBlur, so the selection
              // registers even though blur closes the dropdown.
              onMouseDown={() => handleSelect(place)}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
