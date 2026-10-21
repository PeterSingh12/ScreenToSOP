import json

from fastapi.testclient import TestClient

import api
from storage.jobs import get_job, update_job


def test_health_endpoint():
    client = TestClient(api.app)
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'ok'


def test_record_to_sop_rejects_unsupported_extension(tmp_path, monkeypatch):
    monkeypatch.setattr(api, 'JOBS_DIR', tmp_path / 'jobs')
    monkeypatch.setattr(api, 'DB_PATH', tmp_path / 'jobs.sqlite3')
    client = TestClient(api.app)
    response = client.post('/record-to-sop', files={'video': ('malware.exe', b'not video', 'application/octet-stream')})
    assert response.status_code == 415


def test_record_to_sop_returns_json_and_artifact_links(tmp_path, monkeypatch):
    jobs_dir = tmp_path / 'jobs'
    db_path = tmp_path / 'jobs.sqlite3'
    monkeypatch.setattr(api, 'JOBS_DIR', jobs_dir)
    monkeypatch.setattr(api, 'DB_PATH', db_path)

    def fake_run_job(job_id, job_dir, db_path_arg):
        job_dir = __import__('pathlib').Path(job_dir)
        artifacts = job_dir / 'artifacts'
        artifacts.mkdir(parents=True, exist_ok=True)
        (job_dir / 'sop.docx').write_bytes(b'fake-docx')
        (job_dir / 'sop.md').write_text('# Test SOP\n', encoding='utf-8')
        (artifacts / 'workflow.json').write_text(json.dumps({
            'job_id': job_id,
            'process_name': 'Test Workflow',
            'readiness': 'needs_review',
            'generation_mode': 'local_ocr_draft',
            'steps': [{'step_number': 1, 'action': 'Open the page.'}],
            'warnings': ['Review before use.'],
        }), encoding='utf-8')
        update_job(db_path_arg, job_id, status='complete', progress=1.0, message='SOP ready', output_path=str(job_dir / 'sop.docx'))

    monkeypatch.setattr(api, 'run_job', fake_run_job)
    client = TestClient(api.app)
    response = client.post(
        '/record-to-sop',
        files={'video': ('workflow.mp4', b'fake video bytes', 'video/mp4')},
        data={'process_name': 'Test Workflow'},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['status'] == 'complete'
    assert data['steps'][0]['action'] == 'Open the page.'
    assert data['artifacts']['markdown'].endswith('/sop.md')
    assert client.get(data['artifacts']['markdown']).status_code == 200
    assert client.get(data['artifacts']['docx']).content == b'fake-docx'
    assert client.get(data['artifacts']['workflow_json']).status_code == 200
