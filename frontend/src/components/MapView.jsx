import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

import { MAP_STYLE, MANHATTAN_CENTER, INITIAL_ZOOM } from '../config'
import {
  ensureRouteLayers,
  setRouteData,
  clearRouteData,
  fitToRoutes,
  ensureSegmentLayers,
  setSegments,
  clearSegments,
  setSegmentHighlight,
  SEGMENT_HIT_LAYER,
} from '../lib/mapRoutes'

// queryRenderedFeatures returns properties as strings/values; normalize types.
function normalizeSegment(props) {
  return {
    edge_id: Number(props.edge_id),
    incident_density: Number(props.incident_density),
    lighting_score: Number(props.lighting_score),
    has_lighting_data: props.has_lighting_data === true || props.has_lighting_data === 'true',
  }
}

// Owns the MapLibre map instance and mirrors React state onto it imperatively:
// markers, the two route lines, and the clickable safe-route segments. All map
// mutation lives here; the rest of the app just passes props.
export default function MapView({ origin, destination, routes, onMapClick, onSegmentClick }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const readyRef = useRef(false)
  const originMarkerRef = useRef(null)
  const destMarkerRef = useRef(null)
  const lastFitKeyRef = useRef(null)

  // Keep the latest handlers in refs so the once-registered map listeners always
  // call the current versions (which close over current state).
  const clickHandlerRef = useRef(onMapClick)
  const segmentClickRef = useRef(onSegmentClick)
  useEffect(() => {
    clickHandlerRef.current = onMapClick
    segmentClickRef.current = onSegmentClick
  }, [onMapClick, onSegmentClick])

  // Initialize the map once.
  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: MANHATTAN_CENTER,
      zoom: INITIAL_ZOOM,
    })
    mapRef.current = map

    map.on('load', () => {
      ensureRouteLayers(map)
      ensureSegmentLayers(map)
      readyRef.current = true
    })

    // Hover over a safe-route segment: pointer cursor + highlight that segment.
    map.on('mousemove', SEGMENT_HIT_LAYER, (e) => {
      map.getCanvas().style.cursor = 'pointer'
      if (e.features?.[0]) setSegmentHighlight(map, e.features[0].geometry)
    })
    map.on('mouseleave', SEGMENT_HIT_LAYER, () => {
      map.getCanvas().style.cursor = ''
      setSegmentHighlight(map, null)
    })

    // Unified click: if the click hit a segment, open its detail (and DON'T treat
    // it as a routing click, so it won't set a point / reset). Otherwise it's a
    // normal map click. queryRenderedFeatures tells us which case we're in.
    map.on('click', (e) => {
      const hits = map.queryRenderedFeatures(e.point, { layers: [SEGMENT_HIT_LAYER] })
      if (hits.length > 0) {
        segmentClickRef.current?.(normalizeSegment(hits[0].properties))
      } else {
        clickHandlerRef.current?.(e.lngLat)
      }
    })

    const handleResize = () => map.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      map.remove()
      mapRef.current = null
      readyRef.current = false
    }
  }, [])

  // Origin marker (green).
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (origin) {
      if (!originMarkerRef.current) {
        originMarkerRef.current = new maplibregl.Marker({ color: '#22c55e' })
      }
      originMarkerRef.current.setLngLat([origin.lng, origin.lat]).addTo(map)
    } else if (originMarkerRef.current) {
      originMarkerRef.current.remove()
      originMarkerRef.current = null
    }
  }, [origin])

  // Destination marker (red).
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (destination) {
      if (!destMarkerRef.current) {
        destMarkerRef.current = new maplibregl.Marker({ color: '#ef4444' })
      }
      destMarkerRef.current.setLngLat([destination.lng, destination.lat]).addTo(map)
    } else if (destMarkerRef.current) {
      destMarkerRef.current.remove()
      destMarkerRef.current = null
    }
  }, [destination])

  // Routes: draw both; clear when routes go away. Only fit the view when the
  // endpoint PAIR changes (a new route request) — not on slider/time re-routes,
  // which would make the map jump while the user is tuning. We key the fit off
  // the route's snapped endpoints.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) return
    if (routes?.fast?.geometry && routes?.safe?.geometry) {
      setRouteData(map, routes.fast.geometry, routes.safe.geometry)
      const so = routes.safe.snapped_origin
      const sd = routes.safe.snapped_destination
      const fitKey = `${so.lat},${so.lng}->${sd.lat},${sd.lng}`
      if (fitKey !== lastFitKeyRef.current) {
        fitToRoutes(map, [routes.fast.geometry, routes.safe.geometry])
        lastFitKeyRef.current = fitKey
      }
    } else {
      clearRouteData(map)
      lastFitKeyRef.current = null
    }
  }, [routes])

  // Clickable safe-route segments (with embedded scores). Rebuilt on every route
  // change; clearing also drops any lingering highlight.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) return
    setSegmentHighlight(map, null)
    const segs = routes?.safe?.segments
    if (segs?.length) {
      const features = segs.map((s) => ({
        type: 'Feature',
        geometry: s.geometry,
        properties: {
          edge_id: s.edge_id,
          incident_density: s.incident_density,
          lighting_score: s.lighting_score,
          has_lighting_data: s.has_lighting_data,
        },
      }))
      setSegments(map, features)
    } else {
      clearSegments(map)
    }
  }, [routes])

  return <div ref={containerRef} className="map" />
}
