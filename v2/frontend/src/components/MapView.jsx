import { useEffect, useRef } from 'react'
import { MapContainer, TileLayer, Marker, Polyline, useMapEvents, useMap } from 'react-leaflet'
import L from 'leaflet'

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

// Calls invalidateSize whenever the map container is resized
function MapResizer() {
  const map = useMap()
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}

function ClickHandler({ waypoints, onWaypointsChange }) {
  useMapEvents({
    click(e) {
      onWaypointsChange([...waypoints, [e.latlng.lat, e.latlng.lng]])
    },
    contextmenu(e) {
      if (waypoints.length === 0) return
      e.originalEvent.preventDefault()
      let nearest = 0, minDist = Infinity
      waypoints.forEach(([lat, lng], i) => {
        const d = Math.hypot(lat - e.latlng.lat, lng - e.latlng.lng)
        if (d < minDist) { minDist = d; nearest = i }
      })
      onWaypointsChange(waypoints.filter((_, i) => i !== nearest))
    },
  })
  return null
}

function getSegmentColor(i, al) {
  const isTunnel = al.tunnels.some(t => al.chainage[i] >= t.start_ch && al.chainage[i] <= t.end_ch)
  const isBridge = al.bridges.some(b => al.chainage[i] >= b.start_ch && al.chainage[i] <= b.end_ch)
  if (isTunnel) return '#94a3b8'
  if (isBridge) return '#a78bfa'
  if (al.cut[i] > 0.1) return '#f87171'
  if (al.fill[i] > 0.1) return '#4ade80'
  return '#38bdf8'
}

function TrackLine({ result }) {
  if (!result?.profile) return null
  const pts = result.profile.lat.map((lat, i) => [lat, result.profile.lng[i]])
  const al = result.alignment

  // Group consecutive same-colour stations into single Polylines
  const groups = []
  let current = null
  for (let i = 0; i < pts.length - 1; i++) {
    const color = getSegmentColor(i, al)
    if (!current || current.color !== color) {
      current = { color, pts: [pts[i]] }
      groups.push(current)
    }
    current.pts.push(pts[i + 1])
  }

  return (
    <>
      {groups.map((g, i) => (
        <Polyline key={i} positions={g.pts} color={g.color} weight={3} opacity={0.9} />
      ))}
    </>
  )
}

export default function MapView({ waypoints, onWaypointsChange, result }) {
  return (
    <div className="w-full h-full relative">
      <MapContainer
        center={[-25.5, 134.0]} zoom={5}
        className="w-full h-full"
        style={{ background: '#1a1a2e' }}
        preferCanvas={true}
      >
        <TileLayer
          url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>'
          subdomains="abcd"
          maxZoom={19}
          keepBuffer={4}
        />

        <MapResizer />
        <ClickHandler waypoints={waypoints} onWaypointsChange={onWaypointsChange} />

        {waypoints.map(([lat, lng], i) => (
          <Marker key={i} position={[lat, lng]} icon={waypointIcon} />
        ))}

        {waypoints.length >= 2 && !result && (
          <Polyline positions={waypoints} color="#38bdf8" weight={2}
            dashArray="6 4" opacity={0.6} />
        )}

        <TrackLine result={result} />
      </MapContainer>

      <div className="absolute bottom-2 left-1/2 -translate-x-1/2 bg-navy-900/80 text-slate-400
                      text-xs px-3 py-1 rounded pointer-events-none z-[1000]">
        Left-click to add waypoints · Right-click to remove
      </div>

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
