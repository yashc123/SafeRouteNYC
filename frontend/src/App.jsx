import { useEffect, useRef } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'

// MapTiler API key comes from a Vite env var (frontend/.env: VITE_MAPTILER_KEY=...).
// Vite exposes only vars prefixed with VITE_ to client code via import.meta.env.
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY

// Dark basemap style hosted by MapTiler, keyed by your API key.
const MAP_STYLE = `https://api.maptiler.com/maps/streets-v2-dark/style.json?key=${MAPTILER_KEY}`

// Manhattan, roughly. [lng, lat] order for MapLibre.
const MANHATTAN_CENTER = [-73.97, 40.78]
const INITIAL_ZOOM = 12

export default function App() {
  const containerRef = useRef(null)
  const mapRef = useRef(null)

  useEffect(() => {
    if (mapRef.current) return // guard against React StrictMode double-invoke

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: MANHATTAN_CENTER,
      zoom: INITIAL_ZOOM,
    })
    mapRef.current = map

    // Keep the map sized to the viewport when the window changes.
    const handleResize = () => map.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      map.remove()
      mapRef.current = null
    }
  }, [])

  return <div ref={containerRef} className="map" />
}
