// Central place for frontend config read from Vite env vars.
// Vite only exposes vars prefixed with VITE_ to client code via import.meta.env.

// Backend API base URL — never hardcoded at call sites, so deployment (AWS) is a
// one-line env change. Falls back to the local backend for dev.
export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY

// Dark basemap style (from Phase 0).
export const MAP_STYLE = `https://api.maptiler.com/maps/streets-v2-dark/style.json?key=${MAPTILER_KEY}`

// Default view: centered on the island's N-S midpoint and zoomed so Manhattan is
// the dominant subject. At z11 (~29 m/px) a typical window shows ~23-29 km top to
// bottom, so the ~20 km island fills most of the frame while staying fully visible
// tip-to-tip, with only a modest band of surrounding NJ/Brooklyn/Queens (Manhattan
// is narrow, so some surroundings are unavoidable). z10.5 was correct but too wide
// (island read as a sliver on large monitors). This is still zoomed-out enough that
// fitBounds only zooms IN to frame a long route, keeping that smooth. [lng, lat].
export const MANHATTAN_CENTER = [-73.965, 40.79]
export const INITIAL_ZOOM = 11

// Manhattan is long and narrow, so any full-island view unavoidably includes some
// NJ/Brooklyn/Queens. Rather than fight that with tight view limits (which clamp and
// glitch), we keep the view LOOSE and enforce Manhattan coverage at the CLICK instead
// (the /coverage check + "currently covers Manhattan" toast). maxBounds ([SW, NE]) is
// just a generous NYC-metro box so the user can't wander off into empty tiles far from
// the city; Manhattan sits well inside it, so it never clamps while viewing the island
// or framing a route.
export const MAP_MAX_BOUNDS = [
  [-74.3, 40.45],
  [-73.55, 41.02],
]
// Loose enough that the whole-island view and any route framing never clamp; it only
// gently stops a deliberate zoom-out to the whole region.
export const MAP_MIN_ZOOM = 9

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
