import { useCallback, useEffect, useState } from 'react'
import { postRoute } from '../lib/api'

// Owns the click-to-route state so components (and later sub-steps' controls) can
// read/drive it. State machine on each map click:
//   - no origin yet            -> this click becomes the origin
//   - origin set, no dest yet  -> this click becomes the destination
//   - both already set         -> reset, and this click becomes a new origin
// Whenever origin AND destination are both set, we POST /route automatically.
export function useRouting() {
  const [origin, setOrigin] = useState(null)
  const [destination, setDestination] = useState(null)
  const [routes, setRoutes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleMapClick = useCallback(
    (lngLat) => {
      const point = { lat: lngLat.lat, lng: lngLat.lng }
      setError(null)
      if (!origin || (origin && destination)) {
        // Fresh start: this click is a new origin; clear any prior pair/routes.
        setRoutes(null)
        setDestination(null)
        setOrigin(point)
      } else {
        // Origin set, no destination yet: this click is the destination.
        setDestination(point)
      }
    },
    [origin, destination],
  )

  const reset = useCallback(() => {
    setOrigin(null)
    setDestination(null)
    setRoutes(null)
    setError(null)
  }, [])

  // Fetch the route whenever both endpoints are set.
  useEffect(() => {
    if (!origin || !destination) return
    let cancelled = false
    setLoading(true)
    setError(null)
    postRoute({ origin, destination })
      .then((data) => {
        if (!cancelled) setRoutes(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Could not fetch route.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [origin, destination])

  return { origin, destination, routes, loading, error, handleMapClick, reset }
}
