import { useCallback, useEffect, useRef, useState } from 'react'
import MapView from './components/MapView'
import Legend from './components/Legend'
import StatusPill from './components/StatusPill'
import ControlPanel from './components/ControlPanel'
import RouteCards from './components/RouteCards'
import RouteBreakdown from './components/RouteBreakdown'
import SegmentDetail from './components/SegmentDetail'
import AreaCard from './components/AreaCard'
import AgentPanel from './components/AgentPanel'
import { useRouting } from './hooks/useRouting'
import { useExplore } from './hooks/useExplore'
import { useAgent } from './hooks/useAgent'
import { checkCoverage } from './lib/api'

// Phase 7.5: adds a Route/Explore mode toggle. Route mode = the full routing app.
// Explore mode = tap the map to see an area's safety. Both share the time-of-day
// selector; switching modes preserves each mode's state (routes survive a trip
// into Explore and back).
export default function App() {
  const [mode, setMode] = useState('route')
  const {
    origin,
    destination,
    routes,
    loading,
    error,
    alpha,
    timeOfDay,
    handleMapClick,
    setAlpha,
    setTimeOfDay,
    setOriginPoint,
    setDestinationPoint,
  } = useRouting()

  const explore = useExplore(timeOfDay)
  const [selectedSegment, setSelectedSegment] = useState(null)

  // A re-route or reset invalidates a previously selected segment.
  useEffect(() => {
    setSelectedSegment(null)
  }, [routes])

  // "Route to here": jump back to Route mode with the tapped area as destination.
  const handleRouteHere = (point) => {
    setDestinationPoint({ lat: point.lat, lng: point.lng })
    setMode('route')
  }

  // When the agent produces a route or area, draw it via the EXISTING flow: set the
  // routing/explore inputs and let the app re-run + render it (no duplicate logic).
  const handleAgentResult = (res) => {
    const safe = res.route?.safe
    if (safe?.snapped_origin && safe?.snapped_destination) {
      setMode('route')
      setAlpha(res.route.safe_alpha)
      setTimeOfDay(res.route.time_of_day)
      setOriginPoint(safe.snapped_origin)
      setDestinationPoint(safe.snapped_destination)
    } else if (res.area?.snapped) {
      setMode('explore')
      explore.explore({ lat: res.area.snapped.lat, lng: res.area.snapped.lng })
    }
  }
  const agent = useAgent(handleAgentResult)

  // Out-of-bounds toast (brief, friendly) for clicks off the Manhattan network.
  const [outOfBounds, setOutOfBounds] = useState(false)
  const oobTimerRef = useRef()
  const flashOutOfBounds = useCallback(() => {
    setOutOfBounds(true)
    clearTimeout(oobTimerRef.current)
    oobTimerRef.current = setTimeout(() => setOutOfBounds(false), 4000)
  }, [])

  // Validate a map click against the covered network before acting on it. Applies
  // to both Route (set origin/destination) and Explore (area lookup) taps.
  const handleRouteClick = useCallback(
    async (lngLat) => {
      const cov = await checkCoverage({ lat: lngLat.lat, lng: lngLat.lng })
      if (cov.in_bounds === false) return flashOutOfBounds()
      handleMapClick(lngLat)
    },
    [handleMapClick, flashOutOfBounds],
  )
  const handleExploreClick = useCallback(
    async (lngLat) => {
      const cov = await checkCoverage({ lat: lngLat.lat, lng: lngLat.lng })
      if (cov.in_bounds === false) return flashOutOfBounds()
      explore.explore({ lat: lngLat.lat, lng: lngLat.lng })
    },
    [explore, flashOutOfBounds],
  )

  const inRoute = mode === 'route'

  return (
    <>
      <MapView
        mode={mode}
        origin={origin}
        destination={destination}
        routes={routes}
        explorePoint={explore.point}
        exploreArea={explore.area}
        onMapClick={handleRouteClick}
        onSegmentClick={setSelectedSegment}
        onExploreClick={handleExploreClick}
      />

      {outOfBounds && (
        <div className="oob-toast">
          SafeRouteNYC currently covers Manhattan — please pick a point on the island.
        </div>
      )}

      <div className="left-stack">
        <ControlPanel
          mode={mode}
          alpha={alpha}
          timeOfDay={timeOfDay}
          origin={origin}
          destination={destination}
          onModeChange={setMode}
          onAlphaChange={setAlpha}
          onTimeChange={setTimeOfDay}
          onOriginSelect={setOriginPoint}
          onDestinationSelect={setDestinationPoint}
        />
        <AgentPanel
          onAsk={agent.ask}
          loading={agent.loading}
          answer={agent.answer}
          error={agent.error}
        />
        {inRoute && routes && <RouteBreakdown safe={routes.safe} />}
      </div>

      {inRoute ? (
        <>
          <SegmentDetail
            segment={selectedSegment}
            timeOfDay={timeOfDay}
            onClose={() => setSelectedSegment(null)}
          />
          <RouteCards routes={routes} />
          <StatusPill
            origin={origin}
            destination={destination}
            loading={loading}
            error={error}
          />
          <Legend />
        </>
      ) : (
        <AreaCard
          area={explore.area}
          loading={explore.loading}
          error={explore.error}
          timeOfDay={timeOfDay}
          onRouteHere={handleRouteHere}
          onClose={explore.clear}
        />
      )}
    </>
  )
}
