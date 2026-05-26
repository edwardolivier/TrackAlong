import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

const Plot = createPlotlyComponent(Plotly)

const DARK = {
  paper_bgcolor: '#0f172a',
  plot_bgcolor: '#0f172a',
  font: { color: '#94a3b8', size: 10 },
  margin: { l: 90, r: 40, t: 8, b: 36 },
}

const COLORS = {
  Cut: '#f87171', Fill: '#4ade80', Bridges: '#a78bfa',
  Tunnels: '#94a3b8', Track: '#38bdf8', 'Rail systems': '#34d399', Contingency: '#f59e0b',
}

export default function CostChart({ result }) {
  if (!result?.costs) return null
  const co = result.costs

  const categories = [
    { label: 'Cut',          value: co.subtotal_cut },
    { label: 'Fill',         value: co.subtotal_fill },
    { label: 'Bridges',      value: co.subtotal_bridges },
    { label: 'Tunnels',      value: co.subtotal_tunnels },
    { label: 'Track',        value: co.subtotal_track },
    { label: 'Rail systems', value: co.subtotal_systems },
    { label: 'Contingency',  value: co.contingency_amount },
  ].filter(c => c.value > 0)

  const toM = v => v / 1e6

  const traces = [{
    type: 'bar',
    orientation: 'h',
    x: categories.map(c => toM(c.value)),
    y: categories.map(c => c.label),
    marker: { color: categories.map(c => COLORS[c.label] ?? '#38bdf8') },
    text: categories.map(c => `$${toM(c.value).toFixed(1)}M`),
    textposition: 'outside',
    textfont: { size: 9, color: '#94a3b8' },
    hovertemplate: '%{y}: $%{x:.1f}M<extra></extra>',
  }]

  const totalM = toM(co.total)
  const perKmM = toM(co.total / (result.route_length_km || 1))

  const layout = {
    ...DARK,
    xaxis: { title: 'AUD (millions)', gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    yaxis: { gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    annotations: [{
      text: `Total: $${totalM.toFixed(0)}M  ·  $${perKmM.toFixed(1)}M/km`,
      xref: 'paper', yref: 'paper', x: 1, y: -0.18,
      xanchor: 'right', showarrow: false,
      font: { size: 10, color: '#38bdf8' },
    }],
  }

  return (
    <Plot data={traces} layout={layout} config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%', height: '100%' }} useResizeHandler />
  )
}
