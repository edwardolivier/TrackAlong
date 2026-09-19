# ARTC engineering standards

Documents referenced from the ARTC Track & Civil engineering standards page
(https://extranet.artc.com.au/eng_track-civil_procedure.html) are downloaded
into this folder, one sub-folder per section (e.g. `structures/`, `track/`),
with a `manifest.tsv` listing section, filename, title and source URL.

The files themselves are not committed. To (re)populate this folder run,
from the repository root, on a machine that can reach the ARTC extranet:

```bash
python scripts/fetch_artc_standards.py                      # all sections
python scripts/fetch_artc_standards.py --section structures # Structures only
python scripts/fetch_artc_standards.py --list               # preview without downloading
```
