import { useState, useEffect, useRef } from 'react'
import { initAuth, renderSignInButton, signOut, getToken } from './lib/auth'
import { analyseRoute, optimiseRoute } from './lib/api'
import { DEFAULT_PARAMS, DEFAULT_CORRIDOR } from './lib/presets'
import MapView from './components/MapView'
import ParamsPanel from './components/ParamsPanel'
import ResultsPanel from './components/ResultsPanel'
import ProfileChart from './components/charts/ProfileChart'
import HorizontalChart from './components/charts/HorizontalChart'
import CostChart from './components/charts/CostChart'

export default function App() {
  const [user, setUser] = useState(null)
  const [waypoints, setWaypoints] = useState([])
  const [params, setParams] = useState(DEFAULT_PARAMS)
  const [corridor, setCorridor] = useState(DEFAULT_CORRIDOR)
  const [result, setResult] = useState(null)
  const [status, setStatus] = useState('')
  const [busy, setBusy] = useState(false)
  const [activeTab, setActiveTab] = useState('profile')
  const [showParams, setShowParams] = useState(true)
  const [showResults, setShowResults] = useState(true)
  const signInRef = useRef(null)

  useEffect(() => {
    initAuth({
      onSignIn: (u) => setUser(u),
      onSignOut: () => setUser(null),
    })
  }, [])

  useEffect(() => {
    if (!user && signInRef.current) {
      renderSignInButton(signInRef.current)
    }
  }, [user])

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
      const res = await analyseRoute({ waypoints, params })
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

  if (!user) {
    return (
      <div className="flex h-screen items-center justify-center bg-navy-900">
        <div className="text-center space-y-6">
          <h1 className="text-3xl font-bold text-sky-400">TrackAlong</h1>
          <p className="text-slate-400">Railway alignment analyser</p>
          <div ref={signInRef} />
        </div>
      </div>
    )
  }

  const TABS = ['profile', 'horizontal', 'cost']

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
        <img src={user.picture} alt="" className="w-6 h-6 rounded-full" />
        <span className="text-xs text-slate-400">{user.email}</span>
        <button onClick={signOut} className="text-xs text-slate-500 hover:text-slate-300">Sign out</button>
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
        {/* Params panel */}
        {showParams && (
          <div className="w-72 shrink-0 overflow-y-auto border-r border-navy-700">
            <ParamsPanel params={params} corridor={corridor}
              onParamsChange={setParams} onCorridorChange={setCorridor} />
          </div>
        )}

        {/* Centre: map + charts */}
        <div className="flex flex-col flex-1 overflow-hidden">
          <div className="flex-1 min-h-0">
            <MapView waypoints={waypoints} onWaypointsChange={setWaypoints}
              result={result} />
          </div>

          {result && (
            <div className="h-64 shrink-0 border-t border-navy-700 flex flex-col">
              {/* Chart tabs */}
              <div className="flex border-b border-navy-700 bg-navy-800 shrink-0">
                {TABS.map(t => (
                  <button key={t} onClick={() => setActiveTab(t)}
                    className={`px-4 py-1.5 text-xs capitalize border-r border-navy-700
                      ${activeTab === t
                        ? 'bg-navy-900 text-slate-200'
                        : 'text-slate-400 hover:bg-navy-700'}`}>
                    {t === 'profile' ? 'Vertical Profile'
                      : t === 'horizontal' ? 'Horizontal Alignment'
                      : 'Cost Estimate'}
                  </button>
                ))}
              </div>
              <div className="flex-1 min-h-0">
                {activeTab === 'profile'    && <ProfileChart result={result} />}
                {activeTab === 'horizontal' && <HorizontalChart result={result} params={params} />}
                {activeTab === 'cost'       && <CostChart result={result} />}
              </div>
            </div>
          )}
        </div>

        {/* Results panel */}
        {showResults && result && (
          <div className="w-80 shrink-0 overflow-y-auto border-l border-navy-700">
            <ResultsPanel result={result} />
          </div>
        )}
      </div>
    </div>
  )
}
