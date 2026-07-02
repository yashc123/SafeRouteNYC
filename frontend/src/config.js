// Central place for frontend config read from Vite env vars.
// Vite only exposes vars prefixed with VITE_ to client code via import.meta.env.

// Backend API base URL — never hardcoded at call sites, so deployment (AWS) is a
// one-line env change. Falls back to the local backend for dev.
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY

// Dark basemap style (from Phase 0).
export const MAP_STYLE = `https://api.maptiler.com/maps/streets-v2-dark/style.json?key=${MAPTILER_KEY}`

// Manhattan view defaults. [lng, lat] order for MapLibre.
export const MANHATTAN_CENTER = [-73.97, 40.78]
export const INITIAL_ZOOM = 12

// Keep the map on Manhattan. maxBounds ([SW, NE]) is a Manhattan bbox with ~2-3 km
// of breathing room on each side so the island's edges aren't cut off; minZoom
// stops the user zooming out until Manhattan is lost in the wider region.
export const MAP_MAX_BOUNDS = [
  [-74.05, 40.68],
  [-73.88, 40.89],
]
// z10 fits Manhattan end-to-end (~21 km N-S) in one frame WITH room for fitBounds
// padding on a long cross-island route, while the island still fills ~half the view
// (z9 would show the whole metro and lose the focus). maxBounds keeps panning tight.
export const MAP_MIN_ZOOM = 10

// Route styling — muted gray for the fast route, confident teal for the safe one.
export const ROUTE_COLORS = {
  fast: '#8a9199',
  safe: '#2dd4bf',
}

// Safety-breakdown bar colors. Calm, non-alarmist: teal for lighting (good),
// muted amber for incidents (caution). Never red.
export const COMPONENT_COLORS = {
  lighting: '#2dd4bf',
  incidents: '#e0a458',
}

// Marker colors (also used by the search-field dots so they match the map).
export const MARKER_COLORS = {
  origin: '#22c55e', // green
  destination: '#ef4444', // red
}

// Geocoding bias to Manhattan/NYC: bbox restricts results to the routable area,
// proximity ranks results nearest the center first. [minLon, minLat, maxLon, maxLat].
export const GEOCODE_BBOX = [-74.03, 40.698, -73.9, 40.882]
export const GEOCODE_PROXIMITY = [-73.97, 40.78]
export const GEOCODE_DEBOUNCE_MS = 300

// Safety-vs-speed slider -> alpha mapping.
// The slider is 0..100; alpha is 0..ALPHA_MAX. Max 10 because testing showed
// alpha 3-8 gives the useful safe detours; 10 makes the "Safest" end decisive
// without absurd detours (beyond ~10 paths barely change). Default alpha 3
// matches the backend default (slider at 30%).
export const ALPHA_MAX = 10
export const DEFAULT_ALPHA = 3
export const DEFAULT_TIME_OF_DAY = 'night'
export const TIME_OF_DAY_OPTIONS = ['day', 'evening', 'night']

// Wait this long after the user stops sliding before firing a /route request.
export const SLIDER_DEBOUNCE_MS = 350

export const sliderToAlpha = (value) => Math.round((value / 100) * ALPHA_MAX * 100) / 100
export const alphaToSlider = (alpha) => Math.round((alpha / ALPHA_MAX) * 100)
