import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'

const Plot = createPlotlyComponent(Plotly)

const DARK = {
  paper_bgcolor: '#0f172a',
  plot_bgcolor: '#0f172a',
  font: { color: '#94a3b8', size: 10 },
  margin: { l: 52, r: 52, t: 8, b: 36 },
}

export default function HorizontalChart({ result, params }) {
  if (!result?.cant || !result?.profile) return null
  const ca = result.cant
  const pr = result.profile
  const minR = params?.min_radius_m ?? 400

  // Colour each station by radius compliance
  const colors = ca.radii.map(r => r < minR ? '#f87171' : '#38bdf8')

  // Cap display at 5× min radius for readability
  const displayRadii = ca.radii.map(r => Math.min(r, minR * 5))
  const ch = ca.chainage.map(v => v / 1000)

  const traces = [
    // Plan view: lat vs lng coloured by radius
    {
      x: pr.lng, y: pr.lat,
      type: 'scatter', mode: 'markers',
      name: 'Route',
      marker: { color: colors, size: 3 },
      xaxis: 'x', yaxis: 'y',
      hovertemplate: 'lng: %{x:.4f}<br>lat: %{y:.4f}<extra></extra>',
    },
    // Radius profile
    {
      x: ch, y: displayRadii,
      type: 'scatter', mode: 'lines', name: 'Radius',
      line: { color: '#38bdf8', width: 1.5 },
      xaxis: 'x2', yaxis: 'y2',
    },
    // Min radius threshold line
    {
      x: [ch[0], ch[ch.length - 1]],
      y: [minR, minR],
      type: 'scatter', mode: 'lines', name: `Min ${minR} m`,
      line: { color: '#f87171', width: 1, dash: 'dash' },
      xaxis: 'x2', yaxis: 'y2',
    },
  ]

  const layout = {
    ...DARK,
    grid: { rows: 1, columns: 2, pattern: 'independent' },
    xaxis:  { title: 'Longitude', gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 }, scaleanchor: 'y' },
    yaxis:  { title: 'Latitude',  gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    xaxis2: { title: 'Chainage (km)', gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    yaxis2: { title: 'Radius (m)',    gridcolor: '#1e293b', linecolor: '#334155', tickfont: { size: 9 } },
    legend: { bgcolor: 'rgba(15,23,42,0.8)', bordercolor: '#334155', borderwidth: 1,
              font: { size: 9 }, orientation: 'h', y: -0.2 },
    hovermode: 'closest',
    annotations: [{
      text: `Violations: ${result.alignment.violations?.length ?? 0}`,
      xref: 'paper', yref: 'paper', x: 0.5, y: 1.0,
      showarrow: false, font: { size: 9, color: '#64748b' },
    }],
  }

  return (
    <Plot data={traces} layout={layout} config={{ displayModeBar: false, responsive: true }}
      style={{ width: '100%', height: '100%' }} useResizeHandler />
  )
}
