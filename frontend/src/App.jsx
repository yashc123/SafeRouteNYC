import { useEffect, useState } from 'react'
import MapView from './components/MapView'
import Legend from './components/Legend'
import StatusPill from './components/StatusPill'
import ControlPanel from './components/ControlPanel'
import RouteCards from './components/RouteCards'
import RouteBreakdown from './components/RouteBreakdown'
import SegmentDetail from './components/SegmentDetail'
import { useRouting } from './hooks/useRouting'

// Sub-step 4: adds the safety breakdown. Left stack = controls + route-level
// "why this route" breakdown. Clicking a safe-route segment opens a per-segment
// detail panel (top-right). Segment selection clears whenever the routes change.
export default function App() {
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

  const [selectedSegment, setSelectedSegment] = useState(null)

  // Any re-route or reset invalidates a previously selected segment.
  useEffect(() => {
    setSelectedSegment(null)
  }, [routes])

  return (
    <>
      <MapView
        origin={origin}
        destination={destination}
        routes={routes}
        onMapClick={handleMapClick}
        onSegmentClick={setSelectedSegment}
      />

      <div className="left-stack">
        <ControlPanel
          alpha={alpha}
          timeOfDay={timeOfDay}
          origin={origin}
          destination={destination}
          onAlphaChange={setAlpha}
          onTimeChange={setTimeOfDay}
          onOriginSelect={setOriginPoint}
          onDestinationSelect={setDestinationPoint}
        />
        {routes && <RouteBreakdown safe={routes.safe} />}
      </div>

      <SegmentDetail
        segment={selectedSegment}
        timeOfDay={timeOfDay}
        onClose={() => setSelectedSegment(null)}
      />
      <RouteCards routes={routes} />
      <StatusPill origin={origin} destination={destination} loading={loading} error={error} />
      <Legend />
    </>
  )
}
