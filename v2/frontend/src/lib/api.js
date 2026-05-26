import { getToken } from './auth'

async function _post(path, body) {
  const token = getToken()
  const res = await fetch(path, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export function analyseRoute({ waypoints, params, costBands, doubleTrack, corridorM }) {
  return _post('/api/analyse', {
    waypoints,
    params,
    cost_bands: costBands,
    double_track: doubleTrack ?? false,
    corridor_m: corridorM ?? 30,
    include_geology: true,
    include_land_zones: true,
  })
}

export function optimiseRoute({ waypoints, params, corridor }) {
  return _post('/api/optimise-route', { waypoints, params, corridor })
}
