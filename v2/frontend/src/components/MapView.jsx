import { useEffect } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, useMapEvents, useMap } from 'react-leaflet'
import L from 'leaflet'

// Fix default marker icons (Vite breaks the default asset path)
delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
})

const waypointIcon = new L.Icon({
  iconUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png',
  iconRetinaUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png',
  shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
  iconSize: [20, 33], iconAnchor: [10, 33],
})

function ClickHandler({ onWaypointsChange, waypoints }) {
  useMapEvents({
    click(e) {
      onWaypointsChange([...waypoints, [e.latlng.lat, e.latlng.lng]])
    },
    contextmenu(e) {
      // Right-click removes nearest waypoint
      if (waypoints.length === 0) return
      e.originalEvent.preventDefault()
      let nearest = 0
      let minDist = Infinity
      waypoints.forEach(([lat, lng], i) => {
        const d = Math.hypot(lat - e.latlng.lat, lng - e.latlng.lng)
        if (d < minDist) { minDist = d; nearest = i }
      })
      onWaypointsChange(waypoints.filter((_, i) => i !== nearest))
    },
  })
  return null
}

function TrackLine({ result }) {
  if (!result?.profile) return null
  const pts = result.profile.lat.map((lat, i) => [lat, result.profile.lng[i]])
  const al = result.alignment

  // Build cut/fill segments for colouring
  const segments = []
  for (let i = 0; i < pts.length - 1; i++) {
    const cut = al.cut[i] > 0.1
    const fill = al.fill[i] > 0.1
    const isTunnel = al.tunnels.some(t => al.chainage[i] >= t.start_ch && al.chainage[i] <= t.end_ch)
    const isBridge = al.bridges.some(b => al.chainage[i] >= b.start_ch && al.chainage[i] <= b.end_ch)
    const color = isTunnel ? '#94a3b8' : isBridge ? '#a78bfa' : cut ? '#f87171' : fill ? '#4ade80' : '#38bdf8'
    segments.push({ pts: [pts[i], pts[i + 1]], color })
  }

  return (
    <>
      {segments.map((s, i) => (
        <Polyline key={i} positions={s.pts} color={s.color} weight={3} opacity={0.85} />
      ))}
    </>
  )
}

export default function MapView({ waypoints, onWaypointsChange, result }) {
  // Australia-centred default view
  const center = [-25.5, 134.0]

  return (
    <div className="w-full h-full relative">
      <MapContainer center={center} zoom={5}
        className="w-full h-full"
        style={{ background: '#0f172a' }}>
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        <ClickHandler waypoints={waypoints} onWaypointsChange={onWaypointsChange} />

        {/* Waypoints */}
        {waypoints.map(([lat, lng], i) => (
          <Marker key={i} position={[lat, lng]} icon={waypointIcon} />
        ))}

        {/* Straight line between waypoints before analysis */}
        {waypoints.length >= 2 && !result && (
          <Polyline positions={waypoints} color="#38bdf8" weight={2}
            dashArray="6 4" opacity={0.6} />
        )}

        {/* Analysis track line */}
        <TrackLine result={result} />
      </MapContainer>

      {/* Map hint */}
      <div className="absolute bottom-2 left-1/2 -translate-x-1/2 bg-navy-900/80 text-slate-400
                      text-xs px-3 py-1 rounded pointer-events-none z-[1000]">
        Left-click to add waypoints · Right-click to remove
      </div>

      {/* Legend */}
      {result && (
        <div className="absolute top-2 right-2 bg-navy-900/90 text-xs p-2 rounded z-[1000] space-y-1">
          {[['#f87171','Cut'],['#4ade80','Fill'],['#38bdf8','At grade'],
            ['#94a3b8','Tunnel'],['#a78bfa','Bridge']].map(([c,l]) => (
            <div key={l} className="flex items-center gap-1.5">
              <span className="w-4 h-1.5 rounded" style={{ background: c }} />
              <span className="text-slate-300">{l}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
