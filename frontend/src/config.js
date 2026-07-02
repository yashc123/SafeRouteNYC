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

// Route styling — muted gray for the fast route, confident teal for the safe one.
export const ROUTE_COLORS = {
  fast: '#8a9199',
  safe: '#2dd4bf',
}

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
