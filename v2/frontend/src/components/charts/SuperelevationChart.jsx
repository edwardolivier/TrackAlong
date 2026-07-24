import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

const Plot = createPlotlyComponent(Plotly)

const DARK = {
  paper_bgcolor: '#0f172a',
  plot_bgcolor: '#0f172a',
  font: { color: '#94a3b8', size: 10 },
  margin: { l: 52, r: 52, t: 8, b: 40 },
}

export default function SuperelevationChart({ result, params }) {
  if (!result?.cant) return null
  const ca = result.cant
  const ch = ca.chainage.map(v => v / 1000)
  const maxCant = params?.max_cant_mm ?? 100
  const designV = ca.design_speed_kph

  const traces = [
    { x: ch, y: ca.equilibrium_cant, type: 'scatter', mode: 'lines', name: 'Equilibrium cant',
      line: { color: '#64748b', width: 1, dash: 'dot' } },
    { x: ch, y: ca.actual_cant, type: 'scatter', mode: 'lines', name: 'Applied cant',
      line: { color: '#38bdf8', width: 2 } },
    { x: ch, y: ca.cant_deficiency, type: 'scatter', mode: 'lines', name: 'Cant deficiency',
      line: { color: '#f59e0b', width: 1.5 } },
    { x: [ch[0], ch[ch.length - 1]], y: [maxCant, maxCant], type: 'scatter', mode: 'lines',
      name: `Max cant ${maxCant} mm`, line: { color: '#f87171', width: 1, dash: 'dash' } },
    // Max permissible speed on the secondary axis
    { x: ch, y: ca.max_speed, type: 'scatter', mode: 'lines', name: 'Max speed',
      line: { color: '#4ade80', width: 1.5 }, yaxis: 'y2' },
  ]

  const layout = {
    ...DARK,
    xaxis: { title: 'Chainage (km)', gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    yaxis: { title: 'Cant (mm)', gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    yaxis2: {
      title: 'Speed (km/h)', overlaying: 'y', side: 'right',
      gridcolor: 'transparent', linecolor: '#334155', tickfont: { size: 9 },
      zeroline: false, range: [0, designV ? designV * 1.1 : undefined],
    },
    legend: {
      bgcolor: 'rgba(15,23,42,0.8)', bordercolor: '#334155', borderwidth: 1,
      font: { size: 9 }, orientation: 'h', y: -0.22,
    },
    hovermode: 'x unified',
    annotations: [{
      text: `Design ${designV?.toFixed(0)} km/h · min on route ${ca.min_speed_kph?.toFixed(0)} km/h`,
      xref: 'paper', yref: 'paper', x: 0.5, y: 1.0,
      showarrow: false, font: { size: 9, color: '#64748b' },
    }],
  }

  return (
    <Plot data={traces} layout={layout} config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%', height: '100%' }} useResizeHandler />
  )
}
