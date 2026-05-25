# TrackAlong — Railway Alignment Analyser

A desktop application for designing and analysing railway alignments. Place waypoints on an interactive map, then let the tool optimise and evaluate the route's vertical and horizontal geometry.

## Features

- **Interactive map** — click to place waypoints on a Leaflet map (served via a local web server)
- **Route optimiser** — automatically finds the best corridor between waypoints, balancing directness against terrain gradient
- **Vertical alignment** — LP-based optimiser fits a grade design to the terrain, generates parabolic vertical curves at VIPs
- **Horizontal alignment** — computes curve radii and flags stations below the minimum radius
- **Earthworks** — calculates cut and fill volumes using batter slopes and formation width
- **Structures** — detects tunnel sections (cut > threshold) and bridge/viaduct sections (fill > threshold), logs lengths and positions
- **Results panel** — live stats: route length, max grade, cut/fill volumes, balance ratio, tunnel/bridge counts, violation list

## Layout

```
┌─────────────┬──────────────────────────────┬─────────────┐
│ Params      │  Map (Leaflet)               │ Results     │
│ Panel       ├──────────────────────────────│ Panel       │
│             │  Charts (tabbed)             │             │
│             │  ├─ Vertical Profile         │             │
│             │  └─ Horizontal Alignment     │             │
└─────────────┴──────────────────────────────┴─────────────┘
```

## Project Structure

```
main.py                  Entry point — launches PySide6 app
run.bat                  Windows launcher (double-click to run)
requirements.txt         Python dependencies
config/
  rail_types.json        Rail type presets (geometry constraints)
src/
  gui/
    main_window.py       Main window, analysis orchestration
    map_widget.py        Embedded Leaflet map (QWebEngineView)
    params_panel.py      Left sidebar — rail type + geometry params
    profile_widget.py    Vertical profile + cut/fill chart (Matplotlib)
    horizontal_widget.py Horizontal alignment + radius chart (Matplotlib)
  core/
    elevation.py         Fetches terrain elevation profile (external API)
    optimizer.py         Vertical alignment LP optimiser
    route_optimizer.py   Corridor / route optimiser between waypoints
  web/
    webserver.py         Local HTTP server serving the Leaflet map
    map.html             Leaflet map front-end
```

## Dependencies

| Package | Purpose |
|---------|---------|
| PySide6 | GUI framework |
| numpy | Array maths |
| scipy | LP solver (`linprog`) |
| matplotlib | Profile and alignment charts |
| requests | Elevation API calls |
| pyproj | Coordinate transforms |
| shapely | Geometry operations |

## Running

```bat
run.bat
```

or directly:

```bash
py main.py
```

## Key Concepts

- **K-value** — controls parabolic vertical curve length: `L = K × Δgrade%`. Separate values for crests and sags.
- **Cut trigger** — if the required cut depth exceeds this threshold (default 50 m), the section is classified as a tunnel and excluded from earthwork volumes.
- **Fill trigger** — if required fill exceeds this threshold (default 10 m), the section is classified as a bridge/viaduct.
- **Batter slopes** — expressed as H:V ratio (e.g. 1.5 = 1.5 m horizontal per 1 m vertical), used to compute earthwork cross-section areas.
