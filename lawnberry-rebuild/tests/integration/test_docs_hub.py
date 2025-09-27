import os
import json
from backend.src.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_docs_list_and_get(tmp_path, monkeypatch):
    # Create a temporary docs folder with markdown files
    docs_dir = tmp_path / 'docs'
    docs_dir.mkdir()
    (docs_dir / 'readme.md').write_text('# Readme\nContent here', encoding='utf-8')
    (docs_dir / 'guide' ).mkdir()
    (docs_dir / 'guide' / 'setup.md').write_text('# Setup\nSteps', encoding='utf-8')

    # Monkeypatch the docs root resolver to point to our temp directory
    from backend.src.api import rest as rest_mod
    monkeypatch.setattr(rest_mod, '_docs_root', lambda: docs_dir)

    # List docs
    resp = client.get('/api/v2/docs/list')
    assert resp.status_code == 200
    items = resp.json()
    assert any(i['path'] == 'readme.md' for i in items)
    assert any(i['path'] == 'guide/setup.md' for i in items)

    # Fetch a doc
    resp2 = client.get('/api/v2/docs/readme.md')
    assert resp2.status_code == 200
    assert 'Readme' in resp2.text

    # Path traversal blocked
    resp3 = client.get('/api/v2/docs/../secrets.txt')
    assert resp3.status_code in (400, 404)
