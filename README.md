# TrackAlong

Railway alignment analyser — evaluates proposed rail routes by computing vertical alignment, cut/fill earthworks, tunnel/bridge detection, and construction cost estimates.

## Versions

| Version | Description | Stack |
|---------|-------------|-------|
| [v1](./v1/) | Desktop app | Python 3.14 + PySide6 6.11 |
| [v2](./v2/) | Web app (Cloud Run) | FastAPI + React, deployed on Google Cloud Run |
| [tracker](./tracker/) | Local ticket / improvement tracker (multi-project) | Python stdlib + SQLite |

## Quick start

### v1 — Desktop
```bash
cd v1
pip install -r requirements.txt
python main.py
```

### v2 — Web
See [v2/README.md](./v2/README.md).

### Tracker — local tickets & improvements
```bash
python tracker/server.py   # http://127.0.0.1:8765
```
See [tracker/README.md](./tracker/README.md).
