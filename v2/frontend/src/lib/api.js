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

export function analyseRoute({ waypoints, params, costBands, doubleTrack, land }) {
  return _post('/api/analyse', {
    waypoints,
    params,
    cost_bands: costBands,
    double_track: doubleTrack ?? false,
    corridor_m: land?.corridor_m ?? 30,
    land_category_costs: land?.category_costs ?? null,
    include_geology: true,
    include_land_zones: land?.include ?? true,
  })
}

// Saved routes API (see backend api/routes_store.py)
async function _req(method, path, body) {
  const token = getToken()
  const res = await fetch(path, {
    method,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const listRoutes  = () => _req('GET', '/api/routes')
export const loadRoute   = (id) => _req('GET', `/api/routes/${id}`)
export const deleteRoute = (id) => _req('DELETE', `/api/routes/${id}`)
export const saveRoute   = (record) => _req('POST', '/api/routes', record)

export function optimiseRoute({ waypoints, params, corridor }) {
  return _post('/api/optimise-route', { waypoints, params, corridor })
}
