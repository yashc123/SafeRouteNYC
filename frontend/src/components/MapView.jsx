import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

import { MAP_STYLE, MANHATTAN_CENTER, INITIAL_ZOOM, MARKER_COLORS } from '../config'
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
import { ensureExploreLayers, setExploreArea, clearExploreArea } from '../lib/mapExplore'

const EXPLORE_MARKER_COLOR = '#94a3b8' // neutral slate — not alarmist

// queryRenderedFeatures returns properties as strings/values; normalize types.
function normalizeSegment(props) {
  return {
    edge_id: Number(props.edge_id),
    incident_density: Number(props.incident_density),
    lighting_score: Number(props.lighting_score),
    has_lighting_data: props.has_lighting_data === true || props.has_lighting_data === 'true',
  }
}

// Owns the MapLibre map. Route mode: markers + route lines + clickable segments.
// Explore mode: a neutral marker + a soft shaded footprint. All map mutation lives
// here; the rest of the app passes props and the current `mode`.
export default function MapView({
  mode,
  origin,
  destination,
  routes,
  explorePoint,
  exploreArea,
  onMapClick,
  onSegmentClick,
  onExploreClick,
}) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const readyRef = useRef(false)
  const originMarkerRef = useRef(null)
  const destMarkerRef = useRef(null)
  const exploreMarkerRef = useRef(null)
  const lastFitKeyRef = useRef(null)

  // Latest handlers + mode kept in refs so the once-registered listeners use them.
  const clickHandlerRef = useRef(onMapClick)
  const segmentClickRef = useRef(onSegmentClick)
  const exploreClickRef = useRef(onExploreClick)
  const modeRef = useRef(mode)
  useEffect(() => {
    clickHandlerRef.current = onMapClick
    segmentClickRef.current = onSegmentClick
    exploreClickRef.current = onExploreClick
    modeRef.current = mode
  }, [onMapClick, onSegmentClick, onExploreClick, mode])

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
      ensureExploreLayers(map)
      readyRef.current = true
    })

    // Hover over a safe-route segment (route mode only — in explore the segment
    // source is empty so nothing fires): pointer cursor + highlight.
    map.on('mousemove', SEGMENT_HIT_LAYER, (e) => {
      map.getCanvas().style.cursor = 'pointer'
      if (e.features?.[0]) setSegmentHighlight(map, e.features[0].geometry)
    })
    map.on('mouseleave', SEGMENT_HIT_LAYER, () => {
      map.getCanvas().style.cursor = ''
      setSegmentHighlight(map, null)
    })

    // Unified click, branching on mode:
    //  - Explore: report the tapped point for an area lookup.
    //  - Route: if a segment was hit, open its detail; else it's a routing click.
    map.on('click', (e) => {
      if (modeRef.current === 'explore') {
        exploreClickRef.current?.(e.lngLat)
        return
      }
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

  // Origin marker (green) — route mode only.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (mode === 'route' && origin) {
      if (!originMarkerRef.current) {
        originMarkerRef.current = new maplibregl.Marker({ color: MARKER_COLORS.origin })
      }
      originMarkerRef.current.setLngLat([origin.lng, origin.lat]).addTo(map)
    } else if (originMarkerRef.current) {
      originMarkerRef.current.remove()
      originMarkerRef.current = null
    }
  }, [origin, mode])

  // Destination marker (red) — route mode only.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (mode === 'route' && destination) {
      if (!destMarkerRef.current) {
        destMarkerRef.current = new maplibregl.Marker({ color: MARKER_COLORS.destination })
      }
      destMarkerRef.current.setLngLat([destination.lng, destination.lat]).addTo(map)
    } else if (destMarkerRef.current) {
      destMarkerRef.current.remove()
      destMarkerRef.current = null
    }
  }, [destination, mode])

  // Explore marker (neutral) — explore mode only.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    if (mode === 'explore' && explorePoint) {
      if (!exploreMarkerRef.current) {
        exploreMarkerRef.current = new maplibregl.Marker({ color: EXPLORE_MARKER_COLOR })
      }
      exploreMarkerRef.current.setLngLat([explorePoint.lng, explorePoint.lat]).addTo(map)
    } else if (exploreMarkerRef.current) {
      exploreMarkerRef.current.remove()
      exploreMarkerRef.current = null
    }
  }, [explorePoint, mode])

  // Route lines — route mode only. Fit only when the endpoint pair changes.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) return
    if (mode === 'route' && routes?.fast?.geometry && routes?.safe?.geometry) {
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
  }, [routes, mode])

  // Clickable safe-route segments — route mode only.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) return
    setSegmentHighlight(map, null)
    const segs = mode === 'route' ? routes?.safe?.segments : null
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
  }, [routes, mode])

  // Explore footprint shading — explore mode only.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !readyRef.current) return
    if (mode === 'explore' && exploreArea?.snapped && exploreArea?.radius_m) {
      setExploreArea(map, exploreArea.snapped.lng, exploreArea.snapped.lat, exploreArea.radius_m)
    } else {
      clearExploreArea(map)
    }
  }, [exploreArea, mode])

  return <div ref={containerRef} className="map" />
}
