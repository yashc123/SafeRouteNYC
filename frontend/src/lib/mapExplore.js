// Explore-mode map layer: a soft translucent teal footprint showing the area
// being scored. Calm — never a red danger shade. Add once, then setData to update.
import { circlePolygon } from './geo'

const AREA = { source: 'explore-area', fill: 'explore-area-fill', line: 'explore-area-line' }
const EMPTY = { type: 'FeatureCollection', features: [] }

export function ensureExploreLayers(map) {
  if (map.getSource(AREA.source)) return
  map.addSource(AREA.source, { type: 'geojson', data: EMPTY })
  map.addLayer({
    id: AREA.fill,
    type: 'fill',
    source: AREA.source,
    paint: { 'fill-color': '#2dd4bf', 'fill-opacity': 0.12 },
  })
  map.addLayer({
    id: AREA.line,
    type: 'line',
    source: AREA.source,
    paint: { 'line-color': '#2dd4bf', 'line-opacity': 0.4, 'line-width': 1.5 },
  })
}

export function setExploreArea(map, lng, lat, radiusM) {
  const feature = { type: 'Feature', geometry: circlePolygon(lng, lat, radiusM), properties: {} }
  map.getSource(AREA.source)?.setData(feature)
}

export function clearExploreArea(map) {
  map.getSource(AREA.source)?.setData(EMPTY)
}
