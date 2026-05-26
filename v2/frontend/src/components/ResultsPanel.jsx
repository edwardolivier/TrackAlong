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

export default function ResultsPanel({ result }) {
  if (!result) return null
  const al = result.alignment
  const ca = result.cant
  const co = result.costs
  const geo = result.geology
  const lz = result.land_zones

  const tunnelLen = al.tunnels.reduce((s, t) => s + t.length_m, 0)
  const bridgeLen = al.bridges.reduce((s, b) => s + b.length_m, 0)
  const balanceRatio = al.total_fill_m3 > 0
    ? (al.total_cut_m3 / al.total_fill_m3).toFixed(2) : '—'

  return (
    <div className="text-sm py-2">
      <div className="px-3 py-2 border-b border-navy-700">
        <h2 className="text-sky-400 font-semibold">Results</h2>
      </div>

      <Section title="Geometry">
        <Stat label="Route length"  value={fmt(result.route_length_km)} unit="km" highlight />
        <Stat label="Max grade"     value={fmt(al.max_grade_pct, 2)}    unit="%" />
        <Stat label="Ruling grade"  value={fmt(al.ruling_grade_pct, 2)} unit="%" />
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
        <Stat label="Speed restrictions"    value={ca.speed_restricted_stations}  unit="stations" />
        <Stat label="Twist violations"      value={ca.twist_violation_stations}   unit="stations" />
        <Stat label="Transition violations" value={ca.transition_violation_count} unit="" />
        <Stat label="Min speed"             value={fmt(ca.min_speed_kph, 0)}      unit="km/h" />
      </Section>

      {geo && (
        <Section title="Geology">
          <Stat label="Dominant class" value={geo.dominant_class} unit="" />
          {Object.entries(geo.length_by_class || {}).map(([cls, len]) => (
            <Stat key={cls} label={`Class ${cls}`} value={fmt(len / 1000)} unit="km" />
          ))}
        </Section>
      )}

      {co && (
        <Section title="Cost Estimate (AUD)">
          <Stat label="Earthworks"  value={`$${fmtM(co.subtotal_earthworks)}M`} unit="" />
          <Stat label="Bridges"     value={`$${fmtM(co.subtotal_bridges)}M`}    unit="" />
          <Stat label="Tunnels"     value={`$${fmtM(co.subtotal_tunnels)}M`}    unit="" />
          <Stat label="Track"       value={`$${fmtM(co.subtotal_track)}M`}      unit="" />
          <Stat label="Rail systems" value={`$${fmtM(co.subtotal_systems)}M`}  unit="" />
          <Stat label="Contingency" value={`$${fmtM(co.contingency_amount)}M`}  unit={`(${co.contingency_pct}%)`} />
          <Stat label="TOTAL"       value={`$${fmtM(co.total)}M`}               unit="" highlight />
          <Stat label="Per km"      value={`$${fmtM(co.total / result.route_length_km)}M`} unit="/km" />
        </Section>
      )}

      {lz && lz.total_cost > 0 && (
        <Section title="Land Acquisition">
          <Stat label="Corridor area"  value={fmt(lz.total_area_m2 / 10000)} unit="ha" />
          <Stat label="Est. land cost" value={`$${fmtM(lz.total_cost)}M`}    unit="" />
        </Section>
      )}
    </div>
  )
}
