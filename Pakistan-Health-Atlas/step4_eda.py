"""Step 4: exploratory analysis and downloadable report."""
import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from paths import CHARTS, DATABASE, REJECTED, REPORT
from step1_fetch import PROVINCES
from step3_database import connect, init_database

CHARTS_FOLDER = str(CHARTS)
README_FILE = str(REPORT)  # Legacy compatibility: now writes REPORT, not installation docs.


def run_eda():
    init_database()
    with connect() as conn:
        df = pd.read_sql_query("SELECT * FROM facilities", conn)
    if df.empty:
        return {"message": "No facilities in the database. Fetch and clean first."}

    missing = {
        "city_missing_pct": round(float(df["city"].isna().mean() * 100), 2),
        "operator_type_missing_pct": round(float(df["operator_type"].isna().mean() * 100), 2),
    }
    rejected_count = 0
    if REJECTED.exists():
        try:
            with REJECTED.open("r", encoding="utf-8") as fh:
                rejected_count = len(json.load(fh))
        except (ValueError, TypeError):
            rejected_count = 0

    types = {str(k): int(v) for k, v in df["facility_type"].value_counts().items()}
    counts = df["province"].value_counts().to_dict()
    total_pop = sum(values[2] for values in PROVINCES.values())
    average = round(len(df) / total_pop * 100000, 2)
    regions = []
    for name, _, population in PROVINCES.values():
        count = int(counts.get(name, 0))
        per_100k = round(count / population * 100000, 2)
        regions.append({
            "province": name, "facilities": count,
            "population": population, "per_100k": per_100k,
            "status": "Below mapped average" if per_100k < average else "At or above mapped average",
        })
    regions.sort(key=lambda entry: entry["per_100k"])

    raw_owner = {str(k): int(v) for k, v in df["operator_type"].fillna("missing").value_counts().items()}
    ownership = {str(k): int(v) for k, v in df["ownership"].value_counts().items()}

    CHARTS.mkdir(parents=True, exist_ok=True)
    _bar_chart(types, "Mapped facilities by type", "Facilities", CHARTS / "facility_types.png")
    _bar_chart(ownership, "Ownership (tag / name inferred)", "Facilities", CHARTS / "public_vs_private.png")
    _bar_chart({r["province"]: r["per_100k"] for r in regions},
               "Mapped facilities per 100k residents", "Per 100k", CHARTS / "province_per_100k.png")
    return {
        "total_valid_facilities": len(df),
        "rejected_records": rejected_count,
        "missing_data": missing,
        "facility_types": types,
        "national_avg_per_100k": average,
        "province_distribution": regions,
        "public_vs_private_raw_tag": raw_owner,
        "public_vs_private_inferred": ownership,
        "warning": "OSM shows mapped facilities only. Counts do not establish healthcare access or medical need.",
    }


def _bar_chart(values, title, xlabel, output):
    labels = list(values)
    data = list(values.values())
    fig, ax = plt.subplots(figsize=(9.5, max(3.8, len(labels) * 0.54 + 1.4)))
    fig.patch.set_facecolor("#ffffff")
    ax.barh(labels[::-1], data[::-1], color="#2563eb", height=0.55)
    ax.set_title(title, loc="left", fontsize=14, fontweight="bold", pad=16)
    ax.set_xlabel(xlabel)
    ax.set_axisbelow(True)
    ax.grid(axis="x", alpha=0.15)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    fig.tight_layout(pad=2)
    fig.savefig(output, dpi=160)
    plt.close(fig)


def generate_readme():
    """Generate an EDA report without overwriting the project's setup README."""
    result = run_eda()
    if "message" in result:
        raise RuntimeError(result["message"])
    regions = "\n".join(
        f"| {r['province']} | {r['facilities']} | {r['population']:,} | {r['per_100k']} | {r['status']} |"
        for r in result["province_distribution"]
    )
    types = "\n".join(f"| {k.title()} | {v} |" for k, v in result["facility_types"].items())
    owners = "\n".join(f"| {k.title()} | {v} |" for k, v in result["public_vs_private_inferred"].items())
    report = f"""# Pakistan Health Atlas — Data Analysis Report

> **Interpretation warning:** OpenStreetMap is crowdsourced and incomplete. These numbers
> represent **mapped facilities**, NOT the actual number of health facilities,
> quality of care, geographic accessibility, or a reliable shortage assessment.

## Pipeline

Overpass API → JSON → pandas cleaning → Pydantic validation → SQLite UPSERT → CSV → EDA.

## Quality findings

- Valid facility records in database: **{result['total_valid_facilities']:,}**
- Rejected records in last cleaning batch: **{result['rejected_records']:,}**
- Missing city: **{result['missing_data']['city_missing_pct']}%**
- Missing operator:type: **{result['missing_data']['operator_type_missing_pct']}%**

## Facility categories

| Type | Mapped count |
|---|---:|
{types}

![Facility breakdown](charts/facility_types.png)

## Mapping rate by region

National mapped rate: **{result['national_avg_per_100k']} facilities / 100,000 residents**.
Population values are fixed reference estimates in `step1_fetch.py`; for academic
research, verify the provenance and reference dates for each region.

| Region | Mapped count | Reference population | Mapped / 100k | Relative position |
|---|---:|---:|---:|---|
{regions}

![Regional rate](charts/province_per_100k.png)

## Ownership (approximate)

| Classification | Mapped count |
|---|---:|
{owners}

![Ownership](charts/public_vs_private.png)

`public` and `private` use explicit OpenStreetMap `operator:type` tags when available,
then simple facility-name heuristics. **Unknown** means not enough evidence;
these heuristics can misclassify facilities and are not verified ownership records.

## Limitations

- Facilities missing from OSM are not counted; urban areas can be better mapped.
- Some features lack names or coordinates and are rejected by validation.
- Overpass administrative boundaries and tagging vary across regions.
- Counts are not a measure of patient capacity, service quality, or unmet need.
- Data is a snapshot of when the fetch job ran, not a live registry.
- UPSERT retains previously imported records until explicitly removed.
"""
    REPORT.write_text(report, encoding="utf-8")
    return {"status": "Report generated", "file": "REPORT.md"}
