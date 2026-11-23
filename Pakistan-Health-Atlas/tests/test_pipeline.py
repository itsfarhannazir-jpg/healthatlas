import json
import time

from fastapi.testclient import TestClient


def test_clean_validation_and_upsert(project):
    from step2_clean import clean_and_validate
    from step3_database import save_to_database, dashboard_summary
    valid, bad, summary = clean_and_validate()
    assert summary["total_raw"] == 6
    assert summary["duplicates_removed"] == 1
    assert len(valid) == 3
    assert len(bad) == 2
    assert any("latitude" in ' '.join(record["reasons"]) for record in bad)
    stored = save_to_database(valid)
    assert stored["total_rows_in_sqlite"] == 3
    assert project["csv"].exists()
    assert save_to_database(valid)["total_rows_in_sqlite"] == 3  # UPSERT no duplicated facilities
    summary = dashboard_summary()
    assert summary["total"] == 3
    assert summary["mapped_regions"] == 2
    assert summary["quality"]["city_pct"] < 100


def test_api_routes_filters_and_security(project):
    import server
    client = TestClient(server.app)
    assert client.get('/').status_code == 200
    assert 'Pakistan Health Atlas' in client.get('/').text
    assert client.get('/static/style.css').status_code == 200
    assert client.get('/api/summary').json()['total'] == 0
    assert client.get('/download-csv').status_code == 404
    assert client.get('/charts/secret.txt').status_code == 404
    assert client.get('/facilities?limit=999').status_code == 422
    assert client.get('/facilities?page=0').status_code == 422
    assert client.post('/clean-and-save').status_code == 200
    assert client.get('/facilities?q=lahore').json()['total'] == 1
    assert client.get('/facilities?province=sindh').json()['total'] == 1
    assert client.get('/facilities?facility_type=clinic').json()['total'] == 1
    assert client.get('/facilities?ownership=private').json()['total'] == 1
    assert client.get('/facilities?limit=2&page=2').json()['count'] == 1
    assert client.get('/rejected').json()['total_rejected'] == 2
    assert client.get('/download-csv').status_code == 200
    assert client.post('/api/jobs',json={'action':'fetch','province':'not-real'}).status_code == 422


def test_eda_and_report(project):
    from step2_clean import clean_and_validate
    from step3_database import save_to_database
    from step4_eda import run_eda, generate_readme
    valid, _, _ = clean_and_validate()
    save_to_database(valid)
    stats = run_eda()
    assert stats['total_valid_facilities'] == 3
    assert len(stats['province_distribution']) == 7
    assert 'mapped facilities' in stats['warning']
    assert len(list(project['charts'].glob('*.png'))) == 3
    assert generate_readme()['status'] == 'Report generated'
    report = project['report'].read_text(encoding='utf-8')
    assert 'NOT the actual number' in report
    assert 'Facility categories' in report


def test_background_job_completed(project):
    import server
    client = TestClient(server.app)
    response = client.post('/api/jobs', json={'action':'clean','province':'punjab'})
    assert response.status_code == 202
    result = None
    for _ in range(120):
        result = client.get('/api/jobs/current').json()['job']
        if result['status'] in ('completed','failed'):
            break
        time.sleep(.05)
    assert result['status'] == 'completed', result
    assert result['result']['database']['total_rows_in_sqlite'] == 2
    assert client.get('/api/status').json()['raw_count'] == 2


def test_overpass_fetch_with_mock(tmp_path, monkeypatch):
    import step1_fetch
    monkeypatch.setattr(step1_fetch, 'RAW', tmp_path)
    class Response:
        def raise_for_status(self):
            pass
        def json(self):
            return {'elements': [{'id': 1, 'type': 'node'}]}
    called = []
    def fake_post(url, **kwargs):
        called.append(url)
        assert 'ISO3166-2' in kwargs['data']['data']
        return Response()
    monkeypatch.setattr(step1_fetch.requests, 'post', fake_post)
    result = step1_fetch.fetch_province('punjab')
    assert result['raw_records'] == 1
    assert (tmp_path/'punjab.json').exists()
    assert called
    assert not (tmp_path/'punjab.json.tmp').exists()


def test_fetch_all_partial_failure(tmp_path, monkeypatch):
    import step1_fetch
    def fake_fetch(key):
        if key == 'punjab':
            raise RuntimeError('Temporarily offline')
        return {'province': key, 'status': 'success', 'raw_records': 2}
    monkeypatch.setattr(step1_fetch,'fetch_province',fake_fetch)
    monkeypatch.setattr(step1_fetch.time,'sleep',lambda seconds:None)
    results=step1_fetch.fetch_all_provinces()
    assert len(results) == 7
    assert results[0]['status'] == 'failed'
    assert sum(r['status']=='success' for r in results)==6
