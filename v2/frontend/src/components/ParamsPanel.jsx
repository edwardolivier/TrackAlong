import { RAIL_PRESETS, DEFAULT_CORRIDOR } from '../lib/presets'

function Field({ label, unit, value, onChange, min, max, step = 0.1 }) {
  return (
    <div className="flex items-center justify-between py-0.5">
      <label className="text-xs text-slate-400 flex-1">{label}</label>
      <div className="flex items-center gap-1">
        <input type="number" value={value} step={step} min={min} max={max}
          onChange={e => onChange(parseFloat(e.target.value) || 0)}
          className="w-20 text-right text-xs bg-navy-700 border border-navy-600
                     text-slate-200 rounded px-1.5 py-0.5 focus:outline-none focus:border-sky-500" />
        {unit && <span className="text-xs text-slate-500 w-8">{unit}</span>}
      </div>
    </div>
  )
}

function Section({ title, children, defaultOpen = true }) {
  return (
    <details open={defaultOpen} className="group">
      <summary className="flex items-center gap-1 cursor-pointer px-3 py-1.5
                          bg-navy-800 border-b border-navy-700 text-xs font-semibold
                          text-slate-300 uppercase tracking-wide select-none
                          hover:bg-navy-700 list-none">
        <span className="group-open:rotate-90 transition-transform">▶</span>
        {title}
      </summary>
      <div className="px-3 py-1 border-b border-navy-700 space-y-0.5">
        {children}
      </div>
    </details>
  )
}

export default function ParamsPanel({ params, corridor, onParamsChange, onCorridorChange }) {
  function set(key, val) { onParamsChange({ ...params, [key]: val }) }
  function setC(key, val) { onCorridorChange({ ...corridor, [key]: val }) }

  const presetName = Object.entries(RAIL_PRESETS).find(([, v]) =>
    v.max_grade_pct === params.max_grade_pct &&
    v.min_radius_m === params.min_radius_m &&
    v.design_speed_kph === params.design_speed_kph
  )?.[0] ?? 'Custom'

  function applyPreset(name) {
    if (name === 'Custom') return
    onParamsChange({ ...params, ...RAIL_PRESETS[name] })
  }

  return (
    <div className="text-sm">
      <div className="px-3 py-2 border-b border-navy-700 bg-navy-800">
        <h2 className="text-sky-400 font-semibold text-sm mb-1">Parameters</h2>
        <select value={presetName} onChange={e => applyPreset(e.target.value)}
          className="w-full text-xs bg-navy-700 border border-navy-600 text-slate-200
                     rounded px-2 py-1 focus:outline-none focus:border-sky-500">
          {Object.keys(RAIL_PRESETS).map(n => <option key={n}>{n}</option>)}
          <option>Custom</option>
        </select>
      </div>

      <Section title="Geometry">
        <Field label="Max grade"        unit="%"  value={params.max_grade_pct}     onChange={v => set('max_grade_pct', v)}     step={0.1} min={0.1} max={10} />
        <Field label="Min radius"       unit="m"  value={params.min_radius_m}      onChange={v => set('min_radius_m', v)}      step={50}  min={25}  max={10000} />
        <Field label="K-value crest"    unit=""   value={params.k_crest}           onChange={v => set('k_crest', v)}           step={5}   min={5}   max={500} />
        <Field label="K-value sag"      unit=""   value={params.k_sag}             onChange={v => set('k_sag', v)}             step={5}   min={5}   max={500} />
        <Field label="Formation width"  unit="m"  value={params.formation_width_m} onChange={v => set('formation_width_m', v)} step={0.5} min={4}   max={20} />
        <Field label="Batter cut"       unit="H:V" value={params.batter_cut}       onChange={v => set('batter_cut', v)}        step={0.1} min={0.5} max={5} />
        <Field label="Batter fill"      unit="H:V" value={params.batter_fill}      onChange={v => set('batter_fill', v)}       step={0.1} min={0.5} max={5} />
      </Section>

      <Section title="Speed & Cant">
        <Field label="Design speed"         unit="km/h"     value={params.design_speed_kph}          onChange={v => set('design_speed_kph', v)}          step={5}    min={40}   max={400} />
        <Field label="Gauge"                unit="mm"       value={params.gauge_mm}                  onChange={v => set('gauge_mm', v)}                  step={1}    min={600}  max={1676} />
        <Field label="Max cant"             unit="mm"       value={params.max_cant_mm}               onChange={v => set('max_cant_mm', v)}               step={5}    min={50}   max={200} />
        <Field label="Max cant deficiency"  unit="mm"       value={params.max_cant_deficiency_mm}    onChange={v => set('max_cant_deficiency_mm', v)}    step={5}    min={50}   max={150} />
        <Field label="Cant gradient"        unit="mm/m"     value={params.cant_gradient_max_mm_per_m} onChange={v => set('cant_gradient_max_mm_per_m', v)} step={0.25} min={0.5}  max={5} />
        <Field label="Max twist"            unit="mm/3m"    value={params.max_twist_mm_per_3m}       onChange={v => set('max_twist_mm_per_3m', v)}       step={0.5}  min={2}    max={15} />
      </Section>

      <Section title="Structures">
        <Field label="Tunnel trigger (cut)"  unit="m" value={params.cut_trigger_m}  onChange={v => set('cut_trigger_m', v)}  step={5} min={5}  max={200} />
        <Field label="Bridge trigger (fill)" unit="m" value={params.fill_trigger_m} onChange={v => set('fill_trigger_m', v)} step={1} min={2}  max={50} />
      </Section>

      <Section title="Analysis" defaultOpen={false}>
        <Field label="Ruling grade window" unit="km" value={params.ruling_grade_length_km} onChange={v => set('ruling_grade_length_km', v)} step={1} min={1} max={50} />
      </Section>

      <Section title="Route Optimiser" defaultOpen={false}>
        <Field label="Corridor half-width" unit="km" value={corridor.corridor_km}     onChange={v => setC('corridor_km', v)}     step={5}   min={1}  max={100} />
        <Field label="Layers"              unit=""   value={corridor.num_layers}      onChange={v => setC('num_layers', Math.round(v))}   step={1}   min={3}  max={20} />
        <Field label="Candidates/layer"    unit=""   value={corridor.lateral_steps}   onChange={v => setC('lateral_steps', Math.round(v))} step={2}   min={3}  max={15} />
        <Field label="Grade weight"        unit=""   value={corridor.weight_grade}    onChange={v => setC('weight_grade', v)}    step={1}   min={0.1} max={20} />
      </Section>
    </div>
  )
}
