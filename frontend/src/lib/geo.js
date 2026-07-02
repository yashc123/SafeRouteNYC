// Build a GeoJSON Polygon approximating a circle of `radiusM` meters around a
// lon/lat, for shading the Explore footprint. Small-radius equirectangular
// approximation (good for a few hundred meters in Manhattan).
export function circlePolygon(lng, lat, radiusM, steps = 48) {
  const dLat = radiusM / 111320
  const dLng = radiusM / (111320 * Math.cos((lat * Math.PI) / 180))
  const ring = []
  for (let i = 0; i <= steps; i++) {
    const theta = (i / steps) * 2 * Math.PI
    ring.push([lng + dLng * Math.cos(theta), lat + dLat * Math.sin(theta)])
  }
  return { type: 'Polygon', coordinates: [ring] }
}
