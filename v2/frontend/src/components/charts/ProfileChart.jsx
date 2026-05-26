import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

const Plot = createPlotlyComponent(Plotly)

const DARK = {
  paper_bgcolor: '#0f172a',
  plot_bgcolor: '#0f172a',
  font: { color: '#94a3b8', size: 10 },
  margin: { l: 52, r: 40, t: 8, b: 36 },
}

export default function ProfileChart({ result }) {
  if (!result?.alignment) return null
  const al = result.alignment
  const ch = al.chainage.map(v => v / 1000)  // metres → km

  // Cut/fill shading as filled areas between ground and track
  const cutMask = al.cut.map((c, i) => c > 0.05 ? al.track[i] : null)
  const fillMask = al.fill.map((f, i) => f > 0.05 ? al.track[i] : null)

  const traces = [
    // Ground — filled area
    { x: ch, y: al.ground, type: 'scatter', mode: 'lines', name: 'Ground',
      line: { color: '#64748b', width: 1.5 },
      fill: 'tozeroy', fillcolor: 'rgba(100,116,139,0.15)' },

    // Track
    { x: ch, y: al.track, type: 'scatter', mode: 'lines', name: 'Track',
      line: { color: '#38bdf8', width: 2 } },

    // Cut regions (ground → track where cut > 0)
    { x: ch, y: al.ground, type: 'scatter', mode: 'none', name: 'Cut',
      fill: 'tonexty', fillcolor: 'rgba(248,113,113,0.35)',
      showlegend: true,
      customdata: al.cut, hovertemplate: 'Cut: %{customdata:.1f} m<extra></extra>' },

    // Fill regions
    { x: ch, y: fillMask, type: 'scatter', mode: 'none', name: 'Fill',
      fill: 'tonexty', fillcolor: 'rgba(74,222,128,0.35)',
      showlegend: true },

    // Grade on secondary y-axis
    { x: ch, y: al.grade, type: 'scatter', mode: 'lines', name: 'Grade %',
      line: { color: '#f59e0b', width: 1, dash: 'dot' },
      yaxis: 'y2' },
  ]

  // Tunnel/bridge bands as shapes
  const shapes = []
  for (const t of al.tunnels) {
    shapes.push({
      type: 'rect', xref: 'x', yref: 'paper',
      x0: t.start_ch / 1000, x1: t.end_ch / 1000, y0: 0, y1: 1,
      fillcolor: 'rgba(148,163,184,0.12)', line: { width: 0 },
    })
  }
  for (const b of al.bridges) {
    shapes.push({
      type: 'rect', xref: 'x', yref: 'paper',
      x0: b.start_ch / 1000, x1: b.end_ch / 1000, y0: 0, y1: 1,
      fillcolor: 'rgba(167,139,250,0.12)', line: { width: 0 },
    })
  }

  const layout = {
    ...DARK,
    shapes,
    xaxis: { title: 'Chainage (km)', gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    yaxis: { title: 'Elevation (m)', gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    yaxis2: { title: 'Grade (%)', overlaying: 'y', side: 'right', gridcolor: 'transparent',
               linecolor: '#334155', tickfont: { size: 9 }, zeroline: false },
    legend: { bgcolor: 'rgba(15,23,42,0.8)', bordercolor: '#334155', borderwidth: 1,
              font: { size: 9 }, orientation: 'h', y: -0.2 },
    hovermode: 'x unified',
  }

  return (
    <Plot data={traces} layout={layout} config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%', height: '100%' }} useResizeHandler />
  )
}
