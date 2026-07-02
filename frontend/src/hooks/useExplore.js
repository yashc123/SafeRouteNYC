import { useCallback, useEffect, useState } from 'react'
import { fetchAreaSafety } from '../lib/api'

// Explore-mode state. A tapped point triggers an /area-safety fetch; changing
// time_of_day re-fetches the current point. Independent of routing state.
export function useExplore(timeOfDay) {
  const [point, setPoint] = useState(null) // {lat, lng} tapped
  const [area, setArea] = useState(null) // /area-safety response
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const explore = useCallback((p) => {
    setError(null)
    setPoint(p)
  }, [])

  const clear = useCallback(() => {
    setPoint(null)
    setArea(null)
    setError(null)
  }, [])

  useEffect(() => {
    if (!point) return
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchAreaSafety({ lat: point.lat, lng: point.lng, timeOfDay })
      .then((data) => {
        if (!cancelled) setArea(data)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Could not check this area.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [point, timeOfDay])

  return { point, area, loading, error, explore, clear }
}
