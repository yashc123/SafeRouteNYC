import { useEffect, useState } from 'react'
import MapView from './components/MapView'
import Legend from './components/Legend'
import StatusPill from './components/StatusPill'
import ControlPanel from './components/ControlPanel'
import RouteCards from './components/RouteCards'
import RouteBreakdown from './components/RouteBreakdown'
import SegmentDetail from './components/SegmentDetail'
import AreaCard from './components/AreaCard'
import { useRouting } from './hooks/useRouting'
import { useExplore } from './hooks/useExplore'

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
        onMapClick={handleMapClick}
        onSegmentClick={setSelectedSegment}
        onExploreClick={(lngLat) => explore.explore({ lat: lngLat.lat, lng: lngLat.lng })}
      />

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
