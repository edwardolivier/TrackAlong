import { useState } from 'react'

function Stat({ label, value, unit, highlight }) {
  return (
    <div className="flex justify-between items-baseline py-1 border-b border-navy-700">
      <span className="text-xs text-slate-400">{label}</span>
      <span className={`text-sm font-mono ${highlight ? 'text-sky-400' : 'text-slate-200'}`}>
        {value} <span className="text-xs text-slate-500">{unit}</span>
      </span>
    </div>
  )
}

function Section({ title, children }) {
  return (
    <div className="mb-4">
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-1 px-3 pt-2">
        {title}
      </h3>
      <div className="px-3">{children}</div>
    </div>
  )
}

function StructureRow({ label, color, startCh, endCh, lengthM, depthM }) {
  return (
    <div className="py-1.5 border-b border-navy-700">
      <div className="flex items-center gap-1.5 mb-0.5">
        <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: color }} />
        <span className="text-xs font-medium text-slate-200">{label}</span>
        <span className="ml-auto text-xs font-mono text-sky-400">{fmt(lengthM, 0)} m</span>
      </div>
      <div className="flex gap-3 pl-3.5 text-xs text-slate-500">
        <span>Ch {fmt(startCh / 1000)} – {fmt(endCh / 1000)} km</span>
        <span>Max depth {fmt(depthM, 0)} m</span>
      </div>
    </div>
  )
}

function fmt(n, dp = 1) {
  if (n == null) return '—'
  return Number(n).toLocaleString('en-AU', { maximumFractionDigits: dp, minimumFractionDigits: dp })
}
function fmtM(n) { return fmt(n / 1e6, 2) }

// Tightest curve radius on the route (radii are capped at 50 km; ≥10 km ≈ straight).
function minRadius(radii) {
  if (!radii || radii.length === 0) return null
  const m = Math.min(...radii)
  return m >= 10000 ? null : m
}

export default function ResultsPanel({ result }) {
  if (!result) return null
  const al = result.alignment
  const ca = result.cant
  const co = result.costs
  const geo = result.geology
  const lz = result.land_zones
  const coincident = result.coincident_violations || []

  const tunnelLen = al.tunnels.reduce((s, t) => s + t.length_m, 0)
  const bridgeLen = al.bridges.reduce((s, b) => s + b.length_m, 0)
  const balanceRatio = al.total_fill_m3 > 0
    ? (al.total_cut_m3 / al.total_fill_m3).toFixed(2) : '—'
  const minR = minRadius(ca?.radii)

  return (
    <div className="text-sm py-2">
      <div className="px-3 py-2 border-b border-navy-700 flex items-center">
        <h2 className="text-sky-400 font-semibold flex-1">Results</h2>
        <CopyReportButton result={result} minR={minR} />
      </div>

      <Section title="Geometry">
        <Stat label="Route length"     value={fmt(result.route_length_km)} unit="km" highlight />
        <Stat label="Max grade"        value={fmt(al.max_grade_pct, 2)}    unit="%" />
        <Stat label="Ruling grade"     value={fmt(al.ruling_grade_pct, 2)} unit="%" />
        <Stat label="Grade compensation" value={al.grade_compensation_applied ? 'Yes' : 'No'} unit="" />
      </Section>

      <Section title="Earthworks">
        <Stat label="Total cut"     value={fmt(al.total_cut_m3 / 1000, 0)}  unit="000 m³" />
        <Stat label="Total fill"    value={fmt(al.total_fill_m3 / 1000, 0)} unit="000 m³" />
        <Stat label="Balance ratio" value={balanceRatio}                     unit="cut/fill" />
        {al.geology_applied && <>
          <Stat label="Geology-adj cut"  value={fmt(al.geology_adjusted_cut_m3 / 1000, 0)}  unit="000 m³" />
          <Stat label="Geology-adj fill" value={fmt(al.geology_adjusted_fill_m3 / 1000, 0)} unit="000 m³" />
        </>}
      </Section>

      {ca && (
        <Section title="Horizontal & Speed">
          <Stat label="Min radius found" value={minR == null ? '—' : fmt(minR, 0)} unit={minR == null ? '(straight)' : 'm'} />
          <Stat label="Curves found"     value={ca.curves?.length ?? 0}   unit="" />
          <Stat label="Design speed"     value={fmt(ca.design_speed_kph, 0)} unit="km/h" />
          <Stat label="Min speed on route" value={fmt(ca.min_speed_kph, 0)} unit="km/h" />
        </Section>
      )}

      {/* Tunnels */}
      <Section title={`Tunnels (${al.tunnels.length} · ${fmt(tunnelLen / 1000)} km total)`}>
        {al.tunnels.length === 0
          ? <p className="text-xs text-slate-500 py-1">None</p>
          : al.tunnels.map((t, i) => (
            <StructureRow key={i}
              label={`T${i + 1}`} color="#64748b"
              startCh={t.start_ch} endCh={t.end_ch}
              lengthM={t.length_m} depthM={t.max_depth} />
          ))
        }
      </Section>

      {/* Bridges */}
      <Section title={`Bridges (${al.bridges.length} · ${fmt(bridgeLen / 1000)} km total)`}>
        {al.bridges.length === 0
          ? <p className="text-xs text-slate-500 py-1">None</p>
          : al.bridges.map((b, i) => (
            <StructureRow key={i}
              label={`B${i + 1}`} color="#a78bfa"
              startCh={b.start_ch} endCh={b.end_ch}
              lengthM={b.length_m} depthM={b.max_depth} />
          ))
        }
      </Section>

      <Section title="Alignment Compliance">
        <Stat label="Grade violations"      value={al.violations?.length ?? 0}    unit="" />
        <Stat label="Coincident V+H curves" value={coincident.length}             unit="" />
        <Stat label="Reverse-curve issues"  value={ca.reverse_violation_count}    unit="" />
        <Stat label="Speed restrictions"    value={ca.speed_restricted_stations}  unit="stations" />
        <Stat label="Twist violations"      value={ca.twist_violation_stations}   unit="stations" />
        <Stat label="Transition violations" value={ca.transition_violation_count} unit="" />
      </Section>

      {geo && (
        <Section title="Geology">
          <Stat label="Dominant class" value={geo.dominant_class} unit="" />
          {Object.entries(geo.length_by_class || {}).map(([cls, len]) => (
            <Stat key={cls} label={`Class ${cls}`} value={fmt(len / 1000)} unit="km" />
          ))}
          {geo.risk_notes?.length > 0 && (
            <div className="mt-2 text-xs text-amber-300/80 bg-amber-500/5 border border-amber-500/20 rounded px-2 py-1.5 space-y-1">
              {geo.risk_notes.map((r, i) => <div key={i}>⚠ {r}</div>)}
            </div>
          )}
        </Section>
      )}

      {co && (
        <Section title="Cost Estimate (AUD)">
          <Stat label="Earthworks"   value={`$${fmtM(co.subtotal_earthworks)}M`} unit="" />
          <Stat label="Bridges"      value={`$${fmtM(co.subtotal_bridges)}M`}    unit="" />
          <Stat label="Tunnels"      value={`$${fmtM(co.subtotal_tunnels)}M`}    unit="" />
          <Stat label="Track"        value={`$${fmtM(co.subtotal_track)}M`}      unit="" />
          <Stat label="Rail systems" value={`$${fmtM(co.subtotal_systems)}M`}    unit="" />
          <Stat label="Contingency"  value={`$${fmtM(co.contingency_amount)}M`}  unit={`(${co.contingency_pct}%)`} />
          <Stat label="TOTAL"        value={`$${fmtM(co.total)}M`}               unit="" highlight />
          <Stat label="Per km"       value={`$${fmtM(co.total / result.route_length_km)}M`} unit="/km" />
          <CostBreakdown co={co} />
        </Section>
      )}

      {lz && lz.total_cost > 0 && (
        <Section title="Land Acquisition">
          <Stat label="Corridor area"  value={fmt(lz.total_area_m2 / 10000)} unit="ha" />
          <Stat label="Est. land cost" value={`$${fmtM(lz.total_cost)}M`}    unit="" />
          {lz.zones?.map((z, i) => (
            <Stat key={i} label={z.category} value={`$${fmtM(z.cost)}M`} unit={`${fmt(z.area_m2 / 10000, 1)} ha`} />
          ))}
        </Section>
      )}
    </div>
  )
}

function CopyReportButton({ result, minR }) {
  const [copied, setCopied] = useState(false)

  async function copy() {
    try {
      await navigator.clipboard.writeText(buildReport(result, minR))
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    } catch {
      setCopied(false)
    }
  }

  return (
    <button onClick={copy}
      className="text-xs px-2 py-0.5 rounded bg-navy-700 text-slate-400 hover:bg-navy-600">
      {copied ? 'Copied ✓' : 'Copy report'}
    </button>
  )
}

function buildReport(result, minR) {
  const al = result.alignment
  const ca = result.cant
  const co = result.costs
  const geo = result.geology
  const lz = result.land_zones
  const coincident = result.coincident_violations || []
  const M = v => `$${fmtM(v)}M`
  const L = []

  L.push('TrackAlong — Route Analysis', '='.repeat(30), '')
  L.push(`Route length      : ${fmt(result.route_length_km)} km`)
  L.push(`Max grade         : ${fmt(al.max_grade_pct, 2)} %  (ruling ${fmt(al.ruling_grade_pct, 2)} %)`)
  L.push(`Grade compensation: ${al.grade_compensation_applied ? 'Yes' : 'No'}`, '')

  L.push('EARTHWORKS')
  L.push(`  Total cut   : ${fmt(al.total_cut_m3, 0)} m3`)
  L.push(`  Total fill  : ${fmt(al.total_fill_m3, 0)} m3`)
  L.push(`  Balance     : ${al.total_fill_m3 > 0 ? (al.total_cut_m3 / al.total_fill_m3).toFixed(2) : '—'} cut/fill`, '')

  if (ca) {
    L.push('HORIZONTAL & SPEED')
    L.push(`  Min radius  : ${minR == null ? 'straight' : fmt(minR, 0) + ' m'}`)
    L.push(`  Curves      : ${ca.curves?.length ?? 0}`)
    L.push(`  Design speed: ${fmt(ca.design_speed_kph, 0)} km/h   Min on route: ${fmt(ca.min_speed_kph, 0)} km/h`, '')
  }

  L.push(`STRUCTURES  (tunnels ${al.tunnels.length}, bridges ${al.bridges.length})`)
  al.tunnels.forEach((t, i) => L.push(
    `  T${i + 1}: ch ${fmt(t.start_ch / 1000)}–${fmt(t.end_ch / 1000)} km, ${fmt(t.length_m, 0)} m, max depth ${fmt(t.max_depth, 0)} m`))
  al.bridges.forEach((b, i) => L.push(
    `  B${i + 1}: ch ${fmt(b.start_ch / 1000)}–${fmt(b.end_ch / 1000)} km, ${fmt(b.length_m, 0)} m, max height ${fmt(b.max_depth, 0)} m`))
  L.push('')

  L.push('COMPLIANCE')
  L.push(`  Grade violations     : ${al.violations?.length ?? 0}`)
  L.push(`  Coincident V+H curves: ${coincident.length}`)
  L.push(`  Reverse-curve issues : ${ca?.reverse_violation_count ?? 0}`)
  L.push(`  Speed restrictions   : ${ca?.speed_restricted_stations ?? 0} stations`)
  L.push(`  Twist violations     : ${ca?.twist_violation_stations ?? 0} stations`)
  L.push(`  Transition violations: ${ca?.transition_violation_count ?? 0}`, '')

  if (geo) {
    L.push('GEOLOGY')
    L.push(`  Dominant class: ${geo.dominant_class}`)
    Object.entries(geo.length_by_class || {}).forEach(([c, len]) => L.push(`  Class ${c}: ${fmt(len / 1000)} km`))
    ;(geo.risk_notes || []).forEach(r => L.push(`  ! ${r}`))
    L.push('')
  }

  if (co) {
    L.push('COST ESTIMATE (AUD)')
    L.push(`  Earthworks : ${M(co.subtotal_earthworks)}`)
    L.push(`  Bridges    : ${M(co.subtotal_bridges)}`)
    L.push(`  Tunnels    : ${M(co.subtotal_tunnels)}`)
    L.push(`  Track      : ${M(co.subtotal_track)}`)
    L.push(`  Rail systems: ${M(co.subtotal_systems)}`)
    L.push(`  Contingency: ${M(co.contingency_amount)} (${co.contingency_pct}%)`)
    L.push(`  TOTAL      : ${M(co.total)}  (${M(co.total / result.route_length_km)}/km)`, '')
  }

  if (lz && lz.total_cost > 0) {
    L.push('LAND ACQUISITION')
    L.push(`  Corridor area: ${fmt(lz.total_area_m2 / 10000)} ha`)
    L.push(`  Est. cost    : ${M(lz.total_cost)}`)
  }

  return L.join('\n')
}

function CostBreakdown({ co }) {
  const groups = [
    ['Cut', co.lines_cut], ['Fill', co.lines_fill],
    ['Bridges', co.lines_bridges], ['Tunnels', co.lines_tunnels],
    ['Track', co.lines_track], ['Rail systems', co.lines_systems],
  ].filter(([, lines]) => lines && lines.length > 0)
  if (groups.length === 0) return null

  return (
    <details className="mt-2 group">
      <summary className="cursor-pointer text-xs text-slate-500 hover:text-slate-300 select-none py-1">
        <span className="group-open:rotate-90 inline-block transition-transform">▶</span> Detailed breakdown
      </summary>
      <div className="pl-2 pt-1 space-y-2">
        {groups.map(([title, lines]) => (
          <div key={title}>
            <p className="text-[10px] uppercase tracking-wide text-slate-600">{title}</p>
            {lines.map((l, i) => (
              <div key={i} className="flex justify-between text-[11px] py-0.5 border-b border-navy-800">
                <span className="text-slate-400 truncate pr-2">{l.label}</span>
                <span className="font-mono text-slate-300 shrink-0">${fmtM(l.subtotal)}M</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </details>
  )
}
