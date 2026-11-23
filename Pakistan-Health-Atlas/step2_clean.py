"""Step 2: transform and validate raw OSM records."""
import json
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field, ValidationError

from paths import RAW, REJECTED
from step1_fetch import PROVINCES

REJECTED_FILE = str(REJECTED)
PUBLIC_WORDS = ["dhq", "thq", "bhu", "rhc", "civil", "govt", "government", "cmh", "pims", "jinnah", "mayo"]
PRIVATE_WORDS = ["private", "pvt", "shifa", "aga khan", "doctors hospital", "medical center", "polyclinic", "clinic"]


class Facility(BaseModel):
    facility_id: str = Field(min_length=3)
    name: str = Field(min_length=2)
    facility_type: str = Field(min_length=2)
    province: str = Field(min_length=2)
    city: Optional[str] = None
    operator_type: Optional[str] = None
    ownership: str = "unknown"
    latitude: float = Field(ge=23.5, le=37.2)
    longitude: float = Field(ge=60.8, le=77.9)


def fix_nan(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if pd.isna(value):
        return None
    return value


def get_facility_type(amenity, healthcare):
    raw = str(amenity or healthcare or "other").lower().strip()
    if raw in {"hospital", "clinic", "doctors", "pharmacy", "dentist", "laboratory"}:
        return raw
    if raw in {"centre", "center", "health_centre", "health_center"}:
        return "clinic"
    return "other"


def guess_ownership(operator_type, name):
    if operator_type:
        tag = str(operator_type).lower().strip()
        if tag in {"public", "government"}:
            return "public"
        if tag in {"private"}:
            return "private"
    lower_name = str(name or "").lower()
    if any(word in lower_name for word in PUBLIC_WORDS):
        return "public"
    if any(word in lower_name for word in PRIVATE_WORDS):
        return "private"
    return "unknown"


def clean_and_validate(province_key=None):
    """Validate selected or all cached JSONs; quarantine invalid records."""
    if province_key and province_key not in PROVINCES:
        raise ValueError(f"Unknown province: {province_key}")
    sources = ([RAW / f"{province_key}.json"] if province_key else
               sorted(RAW.glob("*.json")))
    sources = [p for p in sources if p.stem in PROVINCES and p.is_file()]
    if not sources:
        raise FileNotFoundError("No raw JSON was found. Use 'Fetch data' first.")

    rows = []
    for source in sources:
        with source.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
            raise ValueError(f"Malformed raw dataset: {source.name}")
        province_name = PROVINCES[source.stem][0]
        for item in payload["elements"]:
            if not isinstance(item, dict):
                continue
            tags = item.get("tags") or {}
            center = item.get("center") or {}
            if not isinstance(tags, dict):
                tags = {}
            if not isinstance(center, dict):
                center = {}
            rows.append({
                "facility_id": f"{item.get('type', 'unknown')}_{item.get('id', 'missing')}",
                "name": tags.get("name") or tags.get("name:en"),
                "amenity": tags.get("amenity"),
                "healthcare": tags.get("healthcare"),
                "province": province_name,
                "city": tags.get("addr:city") or tags.get("addr:district"),
                "operator_type": tags.get("operator:type"),
                "latitude": item.get("lat") if item.get("lat") is not None else center.get("lat"),
                "longitude": item.get("lon") if item.get("lon") is not None else center.get("lon"),
            })
    if not rows:
        raise ValueError("Downloaded JSON contained no healthcare facilities.")

    df = pd.DataFrame(rows)
    raw_count = len(df)
    df = df.drop_duplicates(subset=["facility_id"], keep="first")
    valid_records, rejected_records = [], []
    for row in df.to_dict("records"):
        name = fix_nan(row["name"])
        operator = fix_nan(row["operator_type"])
        record = {
            "facility_id": fix_nan(row["facility_id"]) or "",
            "name": name or "",
            "facility_type": get_facility_type(fix_nan(row["amenity"]), fix_nan(row["healthcare"])),
            "province": fix_nan(row["province"]) or "",
            "city": fix_nan(row["city"]),
            "operator_type": operator,
            "ownership": guess_ownership(operator, name),
            "latitude": fix_nan(row["latitude"]),
            "longitude": fix_nan(row["longitude"]),
        }
        try:
            obj = Facility(**record)
            valid_records.append(obj.model_dump())
        except ValidationError as exc:
            rejected_records.append({
                "facility_id": record["facility_id"],
                "name": record["name"],
                "province": record["province"],
                "reasons": [f"{'.'.join(map(str, issue['loc']))}: {issue['msg']}" for issue in exc.errors()],
            })

    REJECTED.parent.mkdir(parents=True, exist_ok=True)
    with REJECTED.open("w", encoding="utf-8") as fh:
        json.dump(rejected_records, fh, indent=2, ensure_ascii=False)
    summary = {
        "total_raw": raw_count,
        "after_deduplication": len(df),
        "duplicates_removed": raw_count - len(df),
        "valid_count": len(valid_records),
        "rejected_count": len(rejected_records),
        "rejected_file": "data/rejected/rejected_records.json",
        "source_regions": [p.stem for p in sources],
    }
    return valid_records, rejected_records, summary
