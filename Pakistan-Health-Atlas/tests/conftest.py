import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture
def project(tmp_path, monkeypatch):
    import step2_clean
    import step3_database
    import step4_eda
    import server

    raw = tmp_path / "data" / "raw"
    raw.mkdir(parents=True)
    rejected = tmp_path / "data" / "rejected" / "rejected_records.json"
    database = tmp_path / "data" / "health.db"
    csv = tmp_path / "data" / "health.csv"
    charts = tmp_path / "charts"
    report = tmp_path / "REPORT.md"

    for mod, attr, value in [
        (step2_clean,"RAW",raw),(step2_clean,"REJECTED",rejected),
        (step3_database,"DATABASE",database),(step3_database,"CSV",csv),
        (step4_eda,"REJECTED",rejected),(step4_eda,"CHARTS",charts),
        (step4_eda,"REPORT",report),
        (server,"RAW",raw),(server,"REJECTED",rejected),
        (server,"CSV",csv),(server,"REPORT",report),(server,"CHARTS",charts),
    ]:
        monkeypatch.setattr(mod,attr,value)

    (raw / 'punjab.json').write_text(json.dumps({"elements": [
        {"type":"node","id":101,"lat":31.55,"lon":74.32,"tags":{"name":"Lahore General Hospital","amenity":"hospital","operator:type":"public","addr:city":"Lahore"}},
        {"type":"way","id":202,"center":{"lat":31.4,"lon":74.28},"tags":{"name":"Care Clinic","healthcare":"clinic"}},
        {"type":"node","id":303,"lat":31.5,"lon":74.3,"tags":{"amenity":"clinic"}},
        {"type":"node","id":404,"lat":12.0,"lon":74.3,"tags":{"name":"Invalid location","amenity":"hospital"}},
        {"type":"node","id":101,"lat":31.55,"lon":74.32,"tags":{"name":"Duplicate","amenity":"hospital"}},
    ]}), encoding="utf-8")
    (raw / 'sindh.json').write_text(json.dumps({"elements": [
        {"type":"node","id":505,"lat":24.86,"lon":67.01,"tags":{"name":"Karachi pharmacy","amenity":"pharmacy","addr:city":"Karachi"}},
    ]}), encoding="utf-8")
    return {"root":tmp_path,"raw":raw,"database":database,"csv":csv,"rejected":rejected,"charts":charts,"report":report}
