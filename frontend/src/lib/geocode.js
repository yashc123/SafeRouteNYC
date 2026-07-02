import { MAPTILER_KEY, GEOCODE_BBOX, GEOCODE_PROXIMITY } from '../config'

// MapTiler forward geocoding (search). Endpoint:
//   https://api.maptiler.com/geocoding/{query}.json?key=...
// Returns GeoJSON features; each has center [lon, lat] and place_name.
// We bias to Manhattan/NYC with:
//   - bbox: restricts results to the routable Manhattan box
//   - proximity: ranks results closest to the Manhattan center first
//   - country=us
const GEOCODE_BASE = 'https://api.maptiler.com/geocoding'

export async function searchPlaces(query, signal) {
  const params = new URLSearchParams({
    key: MAPTILER_KEY,
    autocomplete: 'true',
    limit: '5',
    country: 'us',
    bbox: GEOCODE_BBOX.join(','),
    proximity: GEOCODE_PROXIMITY.join(','),
  })
  const url = `${GEOCODE_BASE}/${encodeURIComponent(query)}.json?${params.toString()}`

  const res = await fetch(url, { signal })
  if (!res.ok) throw new Error(`Geocoding failed (HTTP ${res.status})`)
  const data = await res.json()

  return (data.features || []).map((f) => ({
    id: f.id,
    label: f.place_name || f.text,
    lng: f.center[0],
    lat: f.center[1],
  }))
}
