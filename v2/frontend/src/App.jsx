import { useState, useEffect } from 'react'
import { login, logout, isLoggedIn, getToken } from './lib/auth'
import { analyseRoute, optimiseRoute } from './lib/api'
import { DEFAULT_PARAMS, DEFAULT_CORRIDOR, DEFAULT_COST_BANDS, DEFAULT_LAND } from './lib/presets'
import MapView from './components/MapView'
import ParamsPanel from './components/ParamsPanel'
import ResultsPanel from './components/ResultsPanel'
import ProfileChart from './components/charts/ProfileChart'
import HorizontalChart from './components/charts/HorizontalChart'
import SuperelevationChart from './components/charts/SuperelevationChart'
import CostChart from './components/charts/CostChart'

function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      await login(username, password)
      onLogin()
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex h-screen items-center justify-center bg-navy-900">
      <div className="w-80 space-y-6">
        <div className="text-center">
          <h1 className="text-3xl font-bold text-sky-400">TrackAlong</h1>
          <p className="text-slate-500 text-sm mt-1">Railway alignment analyser</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-navy-800 rounded-lg p-6 space-y-4 border border-navy-700">
          <div>
            <label className="text-xs text-slate-400 block mb-1">Username</label>
            <input
              type="text" value={username} onChange={e => setUsername(e.target.value)}
              autoFocus required
              className="w-full bg-navy-900 border border-navy-700 text-slate-200 rounded
                         px-3 py-2 text-sm focus:outline-none focus:border-sky-500"
            />
          </div>
          <div>
            <label className="text-xs text-slate-400 block mb-1">Password</label>
            <input
              type="password" value={password} onChange={e => setPassword(e.target.value)}
              required
              className="w-full bg-navy-900 border border-navy-700 text-slate-200 rounded
                         px-3 py-2 text-sm focus:outline-none focus:border-sky-500"
            />
          </div>

          {error && <p className="text-red-400 text-xs">{error}</p>}

          <button type="submit" disabled={busy}
            className="w-full bg-sky-500 hover:bg-sky-400 disabled:opacity-50
                       text-white font-medium rounded py-2 text-sm transition-colors">
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
      </div>
    </div>
  )
}

export default function App() {
  const [authed, setAuthed] = useState(isLoggedIn())
  const [waypoints, setWaypoints] = useState([])
  const [params, setParams] = useState(DEFAULT_PARAMS)
  const [corridor, setCorridor] = useState(DEFAULT_CORRIDOR)
  const [costBands, setCostBands] = useState(DEFAULT_COST_BANDS)
  const [land, setLand] = useState(DEFAULT_LAND)
  const [doubleTrack, setDoubleTrack] = useState(false)
  const [result, setResult] = useState(null)
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [activeTab, setActiveTab] = useState('profile')
  const [showParams, setShowParams] = useState(true)
  const [showResults, setShowResults] = useState(true)

  if (!authed) {
    return <LoginPage onLogin={() => setAuthed(true)} />
  }

  async function handleOptimise() {
    if (waypoints.length < 2) return
    setBusy(true)
    setStatus('Optimising route corridor…')
    try {
      const res = await optimiseRoute({ waypoints, params, corridor })
      setWaypoints(res.waypoints)
      setStatus('Route optimised. Click Analyse to run full analysis.')
    } catch (e) {
      setStatus(`Error: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function handleAnalyse() {
    if (waypoints.length < 2) return
    setBusy(true)
    setStatus('Fetching elevation profile…')
    try {
      const res = await analyseRoute({ waypoints, params, costBands, doubleTrack, land })
      setResult(res)
      setStatus(`Done — ${res.route_length_km.toFixed(1)} km`)
      setShowResults(true)
    } catch (e) {
      setStatus(`Error: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  function handleClear() {
    setWaypoints([])
    setResult(null)
    setStatus('')
  }

  function handleLogout() {
    logout()
    setAuthed(false)
  }

  const TABS = [
    { key: 'profile', label: 'Vertical Profile' },
    { key: 'horizontal', label: 'Horizontal' },
    { key: 'superelevation', label: 'Superelevation' },
    { key: 'cost', label: 'Cost Estimate' },
  ]

  return (
    <div className="flex flex-col h-screen bg-navy-900 overflow-hidden">
      {/* Header */}
      <header className="flex items-center gap-3 px-4 py-2 bg-navy-800 border-b border-navy-700 shrink-0">
        <span className="text-sky-400 font-bold text-lg tracking-tight">TrackAlong</span>
        <span className="text-navy-600 text-sm">v2</span>
        <div className="flex-1" />

        <button onClick={() => setShowParams(p => !p)}
          className="px-3 py-1 text-xs rounded bg-navy-700 text-slate-400 hover:bg-navy-600">
          {showParams ? '◀ Params' : '▶ Params'}
        </button>

        <button onClick={handleOptimise} disabled={busy || waypoints.length < 2}
          className="px-3 py-1 text-xs rounded bg-navy-700 text-slate-300 hover:bg-navy-600 disabled:opacity-40">
          Optimise Route
        </button>
        <button onClick={handleAnalyse} disabled={busy || waypoints.length < 2}
          className="px-3 py-1 text-xs rounded bg-sky-500 text-white hover:bg-sky-400 disabled:opacity-40 font-medium">
          Analyse Route
        </button>
        <button onClick={handleClear} disabled={busy}
          className="px-3 py-1 text-xs rounded bg-navy-700 text-slate-400 hover:bg-navy-600 disabled:opacity-40">
          Clear
        </button>

        <button onClick={() => setShowResults(r => !r)}
          className="px-3 py-1 text-xs rounded bg-navy-700 text-slate-400 hover:bg-navy-600">
          {showResults ? 'Results ▶' : 'Results ◀'}
        </button>

        <div className="w-px h-5 bg-navy-700" />
        <button onClick={handleLogout} className="text-xs text-slate-500 hover:text-slate-300">Sign out</button>
      </header>

      {/* Status bar */}
      {(status || busy) && (
        <div className="px-4 py-1 bg-navy-800 border-b border-navy-700 text-xs text-slate-400 shrink-0 flex items-center gap-2">
          {busy && <span className="inline-block w-2 h-2 rounded-full bg-sky-400 animate-pulse" />}
          {status}
        </div>
      )}

      {/* Main layout */}
      <div className="flex flex-1 overflow-hidden">
        {showParams && (
          <div className="w-72 shrink-0 overflow-y-auto border-r border-navy-700">
            <ParamsPanel params={params} corridor={corridor} costBands={costBands}
              land={land} doubleTrack={doubleTrack}
              onParamsChange={setParams} onCorridorChange={setCorridor}
              onCostBandsChange={setCostBands} onLandChange={setLand}
              onDoubleTrackChange={setDoubleTrack} />
          </div>
        )}

        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex-1 min-h-0">
            <MapView waypoints={waypoints} onWaypointsChange={setWaypoints} result={result} />
          </div>

          {result && (
            <div className="h-64 shrink-0 border-t border-navy-700 flex flex-col">
              <div className="flex border-b border-navy-700 bg-navy-800 shrink-0">
                {TABS.map(t => (
                  <button key={t.key} onClick={() => setActiveTab(t.key)}
                    className={`px-4 py-1.5 text-xs border-r border-navy-700
                      ${activeTab === t.key ? 'bg-navy-900 text-slate-200' : 'text-slate-400 hover:bg-navy-700'}`}>
                    {t.label}
                  </button>
                ))}
              </div>
              <div className="flex-1 min-h-0">
                {activeTab === 'profile'        && <ProfileChart result={result} />}
                {activeTab === 'horizontal'     && <HorizontalChart result={result} params={params} />}
                {activeTab === 'superelevation' && <SuperelevationChart result={result} params={params} />}
                {activeTab === 'cost'           && <CostChart result={result} />}
              </div>
            </div>
          )}
        </div>

        {showResults && result && (
          <div className="w-80 shrink-0 overflow-y-auto border-l border-navy-700">
            <ResultsPanel result={result} />
          </div>
        )}
      </div>
    </div>
  )
}
