import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

const Plot = createPlotlyComponent(Plotly)

const DARK = {
  paper_bgcolor: '#0f172a',
  plot_bgcolor: '#0f172a',
  font: { color: '#94a3b8', size: 10 },
  margin: { l: 52, r: 48, t: 28, b: 36 },
}

export default function ProfileChart({ result }) {
  if (!result?.alignment) return null
  const al = result.alignment
  const ch = al.chainage.map(v => v / 1000)

  // Mask track line: dashed/grey inside tunnels, normal outside
  const trackNormal = al.track.map((v, i) => {
    const inTunnel = al.tunnels.some(t => al.chainage[i] >= t.start_ch && al.chainage[i] <= t.end_ch)
    return inTunnel ? null : v
  })
  const trackTunnel = al.track.map((v, i) => {
    const inTunnel = al.tunnels.some(t => al.chainage[i] >= t.start_ch && al.chainage[i] <= t.end_ch)
    return inTunnel ? v : null
  })

  const traces = [
    // Ground
    { x: ch, y: al.ground, type: 'scatter', mode: 'lines', name: 'Ground',
      line: { color: '#64748b', width: 1.5 },
      fill: 'tozeroy', fillcolor: 'rgba(100,116,139,0.15)' },

    // Track — normal sections
    { x: ch, y: trackNormal, type: 'scatter', mode: 'lines', name: 'Track',
      line: { color: '#38bdf8', width: 2.5 },
      connectgaps: false },

    // Track — tunnel sections (dashed grey to show underground)
    { x: ch, y: trackTunnel, type: 'scatter', mode: 'lines', name: 'Tunnel alignment',
      line: { color: '#94a3b8', width: 2, dash: 'dash' },
      connectgaps: false, showlegend: true },

    // Cut shading
    { x: ch, y: al.ground, type: 'scatter', mode: 'none', name: 'Cut',
      fill: 'tonexty', fillcolor: 'rgba(248,113,113,0.35)', showlegend: true,
      customdata: al.cut, hovertemplate: 'Cut: %{customdata:.1f} m<extra></extra>' },

    // Fill shading
    { x: ch, y: al.fill.map((f, i) => f > 0.05 ? al.track[i] : null),
      type: 'scatter', mode: 'none', name: 'Fill',
      fill: 'tonexty', fillcolor: 'rgba(74,222,128,0.35)', showlegend: true },

    // Grade — secondary axis
    { x: ch, y: al.grade, type: 'scatter', mode: 'lines', name: 'Grade %',
      line: { color: '#f59e0b', width: 1, dash: 'dot' }, yaxis: 'y2' },
  ]

  // Tunnel shapes — solid coloured bands with border
  const shapes = []
  const annotations = []

  al.tunnels.forEach((t, i) => {
    const x0 = t.start_ch / 1000
    const x1 = t.end_ch / 1000
    shapes.push({
      type: 'rect', xref: 'x', yref: 'paper',
      x0, x1, y0: 0, y1: 1,
      fillcolor: 'rgba(71,85,105,0.35)',
      line: { color: '#64748b', width: 1 },
    })
    annotations.push({
      x: (x0 + x1) / 2, y: 1, xref: 'x', yref: 'paper',
      text: `T${i + 1} ${fmt1(t.length_m)}m`,
      showarrow: false, yanchor: 'bottom',
      font: { size: 8, color: '#94a3b8' },
      bgcolor: 'rgba(15,23,42,0.7)', borderpad: 2,
    })
  })

  al.bridges.forEach((b, i) => {
    const x0 = b.start_ch / 1000
    const x1 = b.end_ch / 1000
    shapes.push({
      type: 'rect', xref: 'x', yref: 'paper',
      x0, x1, y0: 0, y1: 1,
      fillcolor: 'rgba(109,40,217,0.2)',
      line: { color: '#a78bfa', width: 1 },
    })
    annotations.push({
      x: (x0 + x1) / 2, y: 1, xref: 'x', yref: 'paper',
      text: `B${i + 1} ${fmt1(b.length_m)}m`,
      showarrow: false, yanchor: 'bottom',
      font: { size: 8, color: '#a78bfa' },
      bgcolor: 'rgba(15,23,42,0.7)', borderpad: 2,
    })
  })

  const layout = {
    ...DARK,
    shapes,
    annotations,
    xaxis: { title: 'Chainage (km)', gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    yaxis: { title: 'Elevation (m)', gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    yaxis2: { title: 'Grade (%)', overlaying: 'y', side: 'right',
               gridcolor: 'transparent', linecolor: '#334155',
               tickfont: { size: 9 }, zeroline: false },
    legend: { bgcolor: 'rgba(15,23,42,0.8)', bordercolor: '#334155', borderwidth: 1,
              font: { size: 9 }, orientation: 'h', y: -0.22 },
    hovermode: 'x unified',
  }

  return (
    <Plot data={traces} layout={layout} config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%', height: '100%' }} useResizeHandler />
  )
}

function fmt1(n) {
  return Math.round(n).toLocaleString('en-AU')
}
