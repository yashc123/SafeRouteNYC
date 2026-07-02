// Reusable route-drawing helpers for a MapLibre map.
//
// MapLibre model: a "source" holds GeoJSON data; a "layer" says how to paint a
// source. We add the two sources + line layers ONCE (ensureRouteLayers), then to
// show/update/clear routes we only call source.setData(...) — cheap, no layer
// churn. The safe layer is added AFTER the fast layer, so it renders on top where
// they overlap. Keeping this here (not in the component) makes it reusable as
// later sub-steps add more overlays.

import maplibregl from 'maplibre-gl'
import { ROUTE_COLORS } from '../config'

const FAST = { source: 'fast-route', layer: 'fast-route-line' }
const SAFE = { source: 'safe-route', layer: 'safe-route-line' }
const EMPTY = { type: 'FeatureCollection', features: [] }

const lineFeature = (geometry) => ({ type: 'Feature', geometry, properties: {} })

// Add sources + layers if they don't exist yet. Call once, after the style loads.
export function ensureRouteLayers(map) {
  if (!map.getSource(FAST.source)) {
    map.addSource(FAST.source, { type: 'geojson', data: EMPTY })
    map.addLayer({
      id: FAST.layer,
      type: 'line',
      source: FAST.source,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': ROUTE_COLORS.fast, 'line-width': 4, 'line-opacity': 0.85 },
    })
  }
  if (!map.getSource(SAFE.source)) {
    map.addSource(SAFE.source, { type: 'geojson', data: EMPTY })
    map.addLayer({
      id: SAFE.layer,
      type: 'line',
      source: SAFE.source,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      // Thicker + brighter: the safe route is the recommendation.
      paint: { 'line-color': ROUTE_COLORS.safe, 'line-width': 6, 'line-opacity': 0.95 },
    })
  }
}

// Swap in new route geometries (GeoJSON LineStrings from the /route response).
export function setRouteData(map, fastGeometry, safeGeometry) {
  map.getSource(FAST.source)?.setData(lineFeature(fastGeometry))
  map.getSource(SAFE.source)?.setData(lineFeature(safeGeometry))
}

// Clear both routes (used on reset).
export function clearRouteData(map) {
  map.getSource(FAST.source)?.setData(EMPTY)
  map.getSource(SAFE.source)?.setData(EMPTY)
}

// Fit the viewport so every coordinate of the given geometries is visible.
export function fitToRoutes(map, geometries) {
  const bounds = new maplibregl.LngLatBounds()
  for (const geometry of geometries) {
    for (const coord of geometry.coordinates) bounds.extend(coord)
  }
  if (!bounds.isEmpty()) {
    map.fitBounds(bounds, { padding: 80, duration: 700 })
  }
}

// --- Per-segment interaction layers (sub-step 4) ---------------------------
// The safe route's segments are drawn as individual clickable features. A wide,
// fully-transparent "hit" line sits on top for easy hover/click targeting; a
// separate highlight source shows the hovered segment. We keep the visible route
// lines above unchanged — this only adds interaction + a highlight.
const SEGMENTS = { source: 'safe-segments', hit: 'safe-segments-hit' }
const HIGHLIGHT = { source: 'segment-highlight', layer: 'segment-highlight-line' }

// Exported so the map's click handler can query which segment was clicked.
export const SEGMENT_HIT_LAYER = SEGMENTS.hit

export function ensureSegmentLayers(map) {
  if (!map.getSource(HIGHLIGHT.source)) {
    map.addSource(HIGHLIGHT.source, { type: 'geojson', data: EMPTY })
    map.addLayer({
      id: HIGHLIGHT.layer,
      type: 'line',
      source: HIGHLIGHT.source,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      paint: { 'line-color': '#ffffff', 'line-width': 4, 'line-opacity': 0.9 },
    })
  }
  if (!map.getSource(SEGMENTS.source)) {
    map.addSource(SEGMENTS.source, { type: 'geojson', data: EMPTY })
    map.addLayer({
      id: SEGMENTS.hit,
      type: 'line',
      source: SEGMENTS.source,
      layout: { 'line-cap': 'round', 'line-join': 'round' },
      // Invisible but interactive: a fat transparent line = generous click target.
      paint: { 'line-color': '#000000', 'line-width': 16, 'line-opacity': 0 },
    })
  }
}

export function setSegments(map, features) {
  map.getSource(SEGMENTS.source)?.setData({ type: 'FeatureCollection', features })
}

export function clearSegments(map) {
  map.getSource(SEGMENTS.source)?.setData(EMPTY)
  map.getSource(HIGHLIGHT.source)?.setData(EMPTY)
}

export function setSegmentHighlight(map, geometry) {
  map.getSource(HIGHLIGHT.source)?.setData(geometry ? lineFeature(geometry) : EMPTY)
}
