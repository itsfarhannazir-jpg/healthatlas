"""Step 1: acquire healthcare POIs from OpenStreetMap Overpass API."""
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from paths import RAW

# Region populations are reference estimates for comparison, NOT ground-truth
# healthcare coverage. Source labels are explained in the generated report.
PROVINCES = {
    "punjab": ("Punjab", "PK-PB", 127688922),
    "sindh": ("Sindh", "PK-SD", 55696147),
    "kp": ("Khyber Pakhtunkhwa", "PK-KP", 40856097),
    "balochistan": ("Balochistan", "PK-BA", 14894402),
    "islamabad": ("Islamabad Capital Territory", "PK-IS", 2363863),
    "ajk": ("Azad Jammu & Kashmir", "PK-JK", 4333467),
    "gb": ("Gilgit-Baltistan", "PK-GB", 1709049),
}

OVERPASS_URLS = (
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
)
RAW_FOLDER = str(RAW)


def _query(iso_code):
    # Do not insist on admin_level=4; federal / autonomous regions differ.
    # ISO3166-2 is an OSM tag, and completeness varies by region.
    return f'''
    [out:json][timeout:90];
    area["ISO3166-2"="{iso_code}"]["boundary"="administrative"]->.region;
    (
      nwr["amenity"~"^(hospital|clinic|doctors|pharmacy|dentist)$"](area.region);
      nwr["healthcare"](area.region);
    );
    out center;
    '''


def fetch_province(province_key):
    """Fetch one region and atomically save the untouched Overpass JSON."""
    if province_key not in PROVINCES:
        raise ValueError(f"Invalid region: {province_key}. Choose from {', '.join(PROVINCES)}")

    full_name, iso_code, _ = PROVINCES[province_key]
    query = _query(iso_code)
    urls = [x.strip() for x in os.getenv("OVERPASS_ENDPOINTS", "").split(",") if x.strip()] or OVERPASS_URLS
    failures = []
    for url in urls:
        try:
            response = requests.post(
                url,
                data={"data": query},
                timeout=(15, 115),
                headers={"User-Agent": "PakistanHealthAtlas/1.0 (educational OSM analytics)"},
            )
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
                raise ValueError("The server returned an invalid Overpass response")
            if not payload["elements"]:
                raise ValueError("No facilities returned: the region may not be mapped with ISO3166-2")

            RAW.mkdir(parents=True, exist_ok=True)
            destination = RAW / f"{province_key}.json"
            temp = destination.with_suffix(".json.tmp")
            try:
                with temp.open("w", encoding="utf-8") as fh:
                    json.dump(payload, fh, ensure_ascii=False)
                temp.replace(destination)
            finally:
                temp.unlink(missing_ok=True)
            return {
                "province": full_name,
                "raw_records": len(payload["elements"]),
                "saved_file": str(destination.relative_to(RAW.parent.parent)),
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "status": "success",
            }
        except (requests.RequestException, ValueError) as exc:
            failures.append(f"{url}: {str(exc)[:160]}")

    raise RuntimeError(f"Could not fetch {full_name}. " + " | ".join(failures))


def fetch_all_provinces(province_key=None, progress=None):
    """Fetch one or all regions. For all, report individual failures and continue."""
    if province_key and province_key not in PROVINCES:
        raise ValueError(f"Invalid region '{province_key}'.")
    targets = [province_key] if province_key else list(PROVINCES)
    results = []
    success = 0
    for i, key in enumerate(targets):
        if progress:
            progress(f"Fetching {PROVINCES[key][0]} ({i + 1}/{len(targets)})", i, len(targets))
        try:
            item = fetch_province(key)
            success += 1
        except RuntimeError as exc:
            if province_key:
                raise
            item = {"province": PROVINCES[key][0], "status": "failed", "error": str(exc)}
        results.append(item)
        if i < len(targets) - 1:
            time.sleep(2)
    if success == 0:
        raise RuntimeError("All requested regions failed to download. Check internet / Overpass service availability.")
    if progress:
        progress("Download finished", len(targets), len(targets))
    return results
