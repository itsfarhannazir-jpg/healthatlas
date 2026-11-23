# Release Notes — Pakistan Health Atlas v1.0

## Added

- Responsive dashboard with a sidebar and four working sections: Overview, Facilities explorer, Data insights, ETL pipeline.
- Live SQLite-based KPI cards, type bar chart, ownership doughnut, regional comparison and field-quality charts.
- Search, province/type/ownership filters, paginated table, and OSM coordinate links.
- Background pipeline tasks with progress, completion, failure, and partial-download warnings.
- CSV and Markdown findings-report downloads.
- API summary/status/region endpoints and validated pagination.
- Windows and Linux/macOS launch scripts, setup documentation, and automated tests.

## Fixed / improved

- File paths no longer depend on the shell working directory.
- SQLite connection and CSV export use consistent project paths.
- Overpass fetches preserve prior cached JSON on failure and report individual failures.
- Cleanup handles missing or malformed source values more safely and logs rejections.
- Database UPSERT is idempotent; search queries are parameterized.
- Chart downloads are allowlisted to prevent arbitrary file reads.
- Report generation no longer overwrites installation README.md.
- Regional mapping-rate labels no longer claim to prove healthcare shortages.

## QA

- Six automated offline tests passed, including parsing, validation, deduplication, UPSERT, filters, EDA, report generation, mocked Overpass fetch, and background tasks.
- Dashboard checked in a headless browser at desktop and mobile widths with *mock display data* (not included in the downloadable production database).
- The real external Overpass service was not exercised in automated tests; its live availability and mapping coverage cannot be guaranteed.
