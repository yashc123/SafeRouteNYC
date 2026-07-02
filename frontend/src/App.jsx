import MapView from './components/MapView'
import Legend from './components/Legend'
import StatusPill from './components/StatusPill'
import { useRouting } from './hooks/useRouting'

// Sub-step 1: click origin/destination -> POST /route -> draw safe + fast routes.
// Routing state lives in the useRouting hook; MapView renders it onto the map;
// Legend and StatusPill are simple overlays. Later sub-steps add controls that
// hook into this same state.
export default function App() {
  const { origin, destination, routes, loading, error, handleMapClick } = useRouting()

  return (
    <>
      <MapView
        origin={origin}
        destination={destination}
        routes={routes}
        onMapClick={handleMapClick}
      />
      <StatusPill origin={origin} destination={destination} loading={loading} error={error} />
      <Legend />
    </>
  )
}
