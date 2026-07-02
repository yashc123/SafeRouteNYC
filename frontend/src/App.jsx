import MapView from './components/MapView'
import Legend from './components/Legend'
import StatusPill from './components/StatusPill'
import ControlPanel from './components/ControlPanel'
import RouteCards from './components/RouteCards'
import { useRouting } from './hooks/useRouting'

// Sub-step 2: adds the safety-vs-speed slider + time-of-day selector. Routing
// state (incl. alpha / time_of_day) lives in useRouting; ControlPanel drives the
// setters; MapView still just reacts to `routes`.
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
  } = useRouting()

  return (
    <>
      <MapView
        origin={origin}
        destination={destination}
        routes={routes}
        onMapClick={handleMapClick}
      />
      <ControlPanel
        alpha={alpha}
        timeOfDay={timeOfDay}
        onAlphaChange={setAlpha}
        onTimeChange={setTimeOfDay}
      />
      <RouteCards routes={routes} />
      <StatusPill origin={origin} destination={destination} loading={loading} error={error} />
      <Legend />
    </>
  )
}
