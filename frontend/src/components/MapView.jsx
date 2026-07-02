import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

import { MAP_STYLE, MANHATTAN_CENTER, INITIAL_ZOOM } from '../config'
import { ensureRouteLayers, setRouteData, clearRouteData, fitToRoutes } from '../lib/mapRoutes'

// Owns the MapLibre map instance and mirrors React state onto it imperatively:
// markers for origin/destination, and the two route lines. All map mutation lives
// here; the rest of the app just passes props.
export default function MapView({ origin, destination, routes, onMapClick }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const readyRef = useRef(false)
  const originMarkerRef = useRef(null)
  const destMarkerRef = useRef(null)
  const lastFitKeyRef = useRef(null)

  // Keep the latest click handler in a ref so the once-registered map listener
  // always calls the current version (which closes over current state).
  const clickHandlerRef = useRef(onMapClick)
  useEffect(() => {
    clickHandlerRef.current = onMapClick
  }, [onMapClick])

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
      readyRef.current = true
    })
    map.on('click', (e) => clickHandlerRef.current?.(e.lngLat))

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

  return <div ref={containerRef} className="map" />
}
