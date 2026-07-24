import { useEffect } from 'react'
import {
  MapContainer, TileLayer, WMSTileLayer, Marker, Polyline,
  LayersControl, useMapEvents, useMap,
} from 'react-leaflet'
import L from 'leaflet'

const { BaseLayer, Overlay } = LayersControl

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

function routeLengthKm(waypoints) {
  let total = 0
  for (let i = 1; i < waypoints.length; i++) {
    total += L.latLng(waypoints[i - 1]).distanceTo(L.latLng(waypoints[i]))
  }
  return total / 1000
}

function MapResizer() {
  const map = useMap()
  useEffect(() => {
    const observer = new ResizeObserver(() => map.invalidateSize())
    observer.observe(map.getContainer())
    return () => observer.disconnect()
  }, [map])
  return null
}

// Add waypoints on left-click; remove the nearest on right-click.
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

// Auto-fit the view when an analysis result arrives, and expose a manual Fit button.
function FitControl({ waypoints, result }) {
  const map = useMap()

  function bounds() {
    if (result?.profile) {
      return result.profile.lat.map((lat, i) => [lat, result.profile.lng[i]])
    }
    return waypoints
  }

  useEffect(() => {
    if (result?.profile?.lat?.length) {
      const b = bounds()
      if (b.length) map.fitBounds(b, { padding: [30, 30] })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [result])

  function fit() {
    const b = bounds()
    if (b.length >= 2) map.fitBounds(b, { padding: [30, 30] })
    else if (b.length === 1) map.setView(b[0], 12)
  }

  return (
    <button onClick={fit}
      className="absolute top-2 left-14 z-[1000] bg-navy-900/90 hover:bg-navy-800
                 text-slate-300 text-xs px-2 py-1 rounded border border-navy-700">
      Fit
    </button>
  )
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
  function moveWaypoint(index, latlng) {
    const next = waypoints.map((wp, i) => (i === index ? [latlng.lat, latlng.lng] : wp))
    onWaypointsChange(next)
  }

  const lengthKm = waypoints.length >= 2 ? routeLengthKm(waypoints) : 0

  return (
    <div className="w-full h-full relative">
      <MapContainer
        center={[-25.5, 134.0]} zoom={5}
        className="w-full h-full"
        style={{ background: '#1a1a2e' }}
        preferCanvas={true}
      >
        <LayersControl position="topright">
          <BaseLayer checked name="Dark (CARTO)">
            <TileLayer
              url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              attribution='&copy; OpenStreetMap &copy; CARTO' subdomains="abcd" maxZoom={19} keepBuffer={4} />
          </BaseLayer>
          <BaseLayer name="Street (OSM)">
            <TileLayer
              url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              attribution='&copy; OpenStreetMap contributors' maxZoom={19} />
          </BaseLayer>
          <BaseLayer name="Topographic (OpenTopoMap)">
            <TileLayer
              url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png"
              attribution='&copy; OpenTopoMap (CC-BY-SA)' maxZoom={17} />
          </BaseLayer>
          <BaseLayer name="Esri Terrain">
            <TileLayer
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}"
              attribution='Tiles &copy; Esri' maxZoom={19} />
          </BaseLayer>
          <BaseLayer name="Satellite (Esri)">
            <TileLayer
              url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
              attribution='Tiles &copy; Esri' maxZoom={19} />
          </BaseLayer>

          <Overlay name="Geology — National (GA 1:1M)">
            <WMSTileLayer
              url="https://services.ga.gov.au/gis/services/GA_Surface_Geology/MapServer/WMSServer"
              layers="0" format="image/png" transparent opacity={0.45}
              attribution='&copy; Geoscience Australia' />
          </Overlay>
          <Overlay name="Geology — QLD Detail (1:100k)">
            <WMSTileLayer
              url="https://spatial-gis.information.qld.gov.au/arcgis/services/GeoscientificInformation/GeologyRegional/MapServer/WMSServer"
              layers="0" format="image/png" transparent opacity={0.5}
              attribution='&copy; Queensland Government' />
          </Overlay>
        </LayersControl>

        <MapResizer />
        <ClickHandler waypoints={waypoints} onWaypointsChange={onWaypointsChange} />
        <FitControl waypoints={waypoints} result={result} />

        {waypoints.map(([lat, lng], i) => (
          <Marker key={i} position={[lat, lng]} icon={waypointIcon} draggable
            eventHandlers={{ dragend: e => moveWaypoint(i, e.target.getLatLng()) }} />
        ))}

        {waypoints.length >= 2 && !result && (
          <Polyline positions={waypoints} color="#38bdf8" weight={2}
            dashArray="6 4" opacity={0.6} />
        )}

        <TrackLine result={result} />
      </MapContainer>

      <div className="absolute bottom-2 left-1/2 -translate-x-1/2 bg-navy-900/80 text-slate-400
                      text-xs px-3 py-1 rounded pointer-events-none z-[1000]">
        Left-click to add · Right-click to remove · Drag to move
        {lengthKm > 0 && <span className="text-sky-400"> · {lengthKm.toFixed(1)} km</span>}
      </div>

      {result && (
        <div className="absolute bottom-2 right-2 bg-navy-900/90 text-xs p-2 rounded z-[1000] space-y-1">
          {[['#f87171', 'Cut'], ['#4ade80', 'Fill'], ['#38bdf8', 'At grade'],
            ['#94a3b8', 'Tunnel'], ['#a78bfa', 'Bridge']].map(([c, l]) => (
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
