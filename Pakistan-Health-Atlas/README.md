# Pakistan Health Atlas

A modern, responsive **FastAPI + vanilla JavaScript** dashboard for healthcare facilities mapped in Pakistan on **OpenStreetMap**. Includes a five-stage data pipeline with pandas, Pydantic, SQLite, CSV, and exploratory analysis. The interface works without a frontend build system.

## Quick start

**Windows:** Double-click `Start_Windows.bat` to create a virtual environment, install missing requirements, and open the dashboard. **Linux/macOS:** Run `bash start_linux_mac.sh`. You can also use the manual commands below.

Requires **Python 3.10+** and an internet connection if you want to fetch real Overpass data.

```bash
# From this folder (where server.py lives):
python -m venv .venv

# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
uvicorn server:app --reload
```

Open **http://127.0.0.1:8000** for the dashboard. FastAPI interactive docs: **http://127.0.0.1:8000/docs**.

The UI is served directly by FastAPI. No npm, Node, or separate frontend server is needed. A Google Fonts connection is optional; system fonts are used if offline.

## Using the dashboard

1. **ETL pipeline → Choose a region** (or all seven) → **Fetch**. Overpass API access can take time; the dashboard remains responsive and shows task progress.
2. **Clean, validate & save**: reads cached JSON, cleans with pandas, validates Pydantic fields, quarantines rejected records, UPSERTs SQLite and exports CSV.
3. **Run exploratory analysis**: creates three PNG charts in `charts/`.
4. **Generate findings report**: writes `REPORT.md` (does not overwrite these instructions).
5. Explore **Overview**, **Facilities explorer**, and **Data insights**. Search, filter, page through records, and download CSV/report.

**Run full pipeline** executes all steps in sequence. If some regions fail during a multi-region fetch, their failures appear as warnings in the job result and on the Pipeline page; successfully fetched regions still proceed. If every region fails, the job stops with an error.

The UI only shows real data when you have imported it. The ZIP contains **no fake dashboard statistics or fabricated healthcare facilities**.

## API

| Endpoint | Purpose |
|---|---|
| `GET /` | Interactive dashboard |
| `GET /docs` | FastAPI Swagger UI |
| `GET /api/summary` | Totals, categories, region rates, quality |
| `GET /api/status` | Cached files and current pipeline job |
| `POST /api/jobs` | Start `fetch`, `clean`, `analyze`, `report`, or `all` task |
| `GET /api/jobs/current` | Poll job progress |
| `GET /facilities?limit=12&page=1&q=...` | Paginated, filterable search |
| `GET /rejected?limit=50` | Rejected records and validation errors |
| `GET /eda` | Current statistics (also generates charts) |
| `GET /download-csv` | CSV output, once available |
| `GET /download-report` | Generated Markdown report |
| `GET /charts/{chart_name}` | One of three generated charts |
| `POST /fetch?province=punjab` | Legacy synchronous fetch |
| `POST /clean-and-save` | Legacy synchronous process |
| `POST /run-all` | Legacy synchronous full pipeline |
| `POST /make-readme` | Legacy endpoint; writes `REPORT.md` |

Example API pipeline request:

```bash
curl -X POST http://127.0.0.1:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"action":"all","province":"punjab"}'
```

Accepted region keys: `punjab`, `sindh`, `kp`, `balochistan`, `islamabad`, `ajk`, `gb`. Sending `null` or omitting `province` processes all configured regions for fetching; clean defaults to processing every cached JSON file.

## Project structure

```
Pakistan-Health-Atlas/
├── server.py                 # REST API, static UI, async background job execution
├── paths.py                  # Absolute paths, independent of working directory
├── step1_fetch.py            # Overpass API download
├── step2_clean.py            # pandas + Pydantic validation
├── step3_database.py         # SQLite, upsert, CSV, filters and summary
├── step4_eda.py              # statistics, chart PNGs, REPORT.md
├── static/
│   ├── index.html            # Responsive dashboard
│   ├── style.css             # Design system + layouts
│   └── app.js                # API integration, charts, table and jobs
├── data/raw/                 # Downloaded OSM JSON (generated)
├── data/rejected/            # Quarantined records (generated)
├── charts/                   # Generated EDA charts
├── tests/                    # Offline automated tests with fixture data
├── requirements.txt
├── requirements-dev.txt
├── Start_Windows.bat
└── start_linux_mac.sh
```

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Tests use fabricated **test fixtures only** (not inserted into production on startup) and mock remote downloads; they **do not need internet**.

## Design and reliability notes

- The frontend has no runtime JS framework dependency; visualizations are drawn from API data using HTML/CSS.
- Paths are relative to the installed project directory, never the terminal's current directory.
- API pagination validates `limit` and `page`, and SQLite searches use parameterized queries.
- The chart endpoint only serves allowlisted PNG names.
- Import jobs run in a background thread so browsers can poll progress. **Use one Uvicorn worker**: in-memory job state does not coordinate across multiple worker processes, and tasks are not durable across server restarts.
- Live Overpass availability, rate limits, OSM region tags, and the accuracy of source data cannot be guaranteed. Download failures are displayed rather than misrepresented as successes. Optional `OVERPASS_ENDPOINTS` comma-separated environment variable overrides the default mirrors.
- The seven population values in `step1_fetch.py` are configurable **reference estimates**, not dynamically verified official figures. Verify them before publishing analysis.
- Facility counts include only named, coordinate-valid OSM features. Missing source records make apparent regional comparisons unreliable; **low counts must not be interpreted as verified healthcare shortages**.
- Ownership is either taken from `operator:type` or inferred heuristically from names. Unknown ownership is preserved.
- The UPSERT design preserves records previously loaded from other regions; it does **not** automatically delete records removed from OSM. To rebuild from scratch, stop the server, back up data, remove `data/pakistan_health.db`, then restart and process your JSON files.

Data © OpenStreetMap contributors, available under ODbL. This is an educational data exploration tool, not a clinical or public-health decision system.
