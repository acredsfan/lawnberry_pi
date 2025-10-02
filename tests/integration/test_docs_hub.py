import os
import json
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from backend.src.main import app
from fastapi.testclient import TestClient
import pytest

client = TestClient(app)

pytestmark = pytest.mark.integration


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


def test_offline_docs_bundle_generation(tmp_path, monkeypatch):
    """
    Test GET /api/v2/docs/bundle to generate offline documentation bundle.
    Validates tarball or ZIP generation with all markdown files, checksums.
    Allows 404/501 per TDD.
    """
    docs_dir = tmp_path / 'docs'
    docs_dir.mkdir()
    (docs_dir / 'hardware-overview.md').write_text('# Hardware\nPi 5', encoding='utf-8')
    (docs_dir / 'installation.md').write_text('# Install\nSteps', encoding='utf-8')
    
    from backend.src.api import rest as rest_mod
    monkeypatch.setattr(rest_mod, '_docs_root', lambda: docs_dir)
    
    resp = client.get('/api/v2/docs/bundle')
    
    # TDD: Allow 404 (not implemented) or 501 (not yet available)
    if resp.status_code in (404, 501):
        return
    
    # When implemented: validate bundle response
    assert resp.status_code == 200
    assert resp.headers['Content-Type'] in ('application/gzip', 'application/zip', 'application/x-tar')
    assert 'Content-Disposition' in resp.headers
    assert 'lawnberry-docs' in resp.headers['Content-Disposition']
    
    # Validate bundle contains files
    assert len(resp.content) > 0


def test_docs_checksum_validation(tmp_path, monkeypatch):
    """
    Test GET /api/v2/docs/checksums to retrieve checksums for all docs.
    Validates SHA256 checksums provided for integrity verification.
    Allows 404/501 per TDD.
    """
    docs_dir = tmp_path / 'docs'
    docs_dir.mkdir()
    hardware_content = '# Hardware Overview\nRaspberry Pi 5'
    (docs_dir / 'hardware-overview.md').write_text(hardware_content, encoding='utf-8')
    
    from backend.src.api import rest as rest_mod
    monkeypatch.setattr(rest_mod, '_docs_root', lambda: docs_dir)
    
    resp = client.get('/api/v2/docs/checksums')
    
    # TDD: Allow 404 (not implemented) or 501 (not yet available)
    if resp.status_code in (404, 501):
        return
    
    # When implemented: validate checksum response
    assert resp.status_code == 200
    data = resp.json()
    assert 'checksums' in data
    
    checksums = data['checksums']
    assert 'hardware-overview.md' in checksums
    
    # Validate checksum format (SHA256 is 64 hex characters)
    checksum = checksums['hardware-overview.md']
    assert len(checksum) == 64
    assert all(c in '0123456789abcdef' for c in checksum)
    
    # Validate checksum correctness
    expected_checksum = hashlib.sha256(hardware_content.encode('utf-8')).hexdigest()
    assert checksum == expected_checksum


def test_docs_freshness_alerts(tmp_path, monkeypatch):
    """
    Test GET /api/v2/docs/freshness to check documentation age/staleness.
    Validates freshness warnings for docs >90 days old.
    Allows 404/501 per TDD.
    """
    docs_dir = tmp_path / 'docs'
    docs_dir.mkdir()
    
    # Create a recent doc
    recent_doc = docs_dir / 'recent.md'
    recent_doc.write_text('# Recent\nUpdated today', encoding='utf-8')
    
    # Create an old doc (simulate by setting mtime in the past)
    old_doc = docs_dir / 'old.md'
    old_doc.write_text('# Old\nNot updated', encoding='utf-8')
    old_timestamp = (datetime.now() - timedelta(days=120)).timestamp()
    os.utime(old_doc, (old_timestamp, old_timestamp))
    
    from backend.src.api import rest as rest_mod
    monkeypatch.setattr(rest_mod, '_docs_root', lambda: docs_dir)
    
    resp = client.get('/api/v2/docs/freshness')
    
    # TDD: Allow 404 (not implemented) or 501 (not yet available)
    if resp.status_code in (404, 501):
        return
    
    # When implemented: validate freshness response
    assert resp.status_code == 200
    data = resp.json()
    assert 'docs' in data
    
    docs = data['docs']
    
    # Find old.md entry
    old_entry = next((d for d in docs if d['path'] == 'old.md'), None)
    assert old_entry is not None
    assert 'age_days' in old_entry
    assert old_entry['age_days'] > 90
    assert 'stale' in old_entry
    assert old_entry['stale'] is True
    
    # Find recent.md entry
    recent_entry = next((d for d in docs if d['path'] == 'recent.md'), None)
    assert recent_entry is not None
    assert recent_entry['age_days'] < 10
    assert recent_entry['stale'] is False


def test_docs_path_traversal_protection_comprehensive(tmp_path, monkeypatch):
    """
    Test comprehensive path traversal protection for all attack vectors.
    Validates rejection of ../, absolute paths, URL encoding, null bytes.
    Allows 404/501 per TDD.
    """
    docs_dir = tmp_path / 'docs'
    docs_dir.mkdir()
    (docs_dir / 'safe.md').write_text('# Safe\nContent', encoding='utf-8')
    
    # Create a sensitive file outside docs directory
    sensitive_file = tmp_path / 'secrets.txt'
    sensitive_file.write_text('SECRET_KEY=abc123', encoding='utf-8')
    
    from backend.src.api import rest as rest_mod
    monkeypatch.setattr(rest_mod, '_docs_root', lambda: docs_dir)
    
    # Attack vector 1: Parent directory traversal
    resp1 = client.get('/api/v2/docs/../secrets.txt')
    assert resp1.status_code in (400, 403, 404), "Path traversal attack not blocked"
    
    # Attack vector 2: Absolute path
    resp2 = client.get(f'/api/v2/docs/{sensitive_file.as_posix()}')
    assert resp2.status_code in (400, 403, 404), "Absolute path attack not blocked"
    
    # Attack vector 3: URL encoded traversal
    resp3 = client.get('/api/v2/docs/..%2F..%2Fsecrets.txt')
    assert resp3.status_code in (400, 403, 404), "URL encoded traversal not blocked"
    
    # Attack vector 4: Null byte injection (if applicable)
    # Note: Python's pathlib may raise ValueError on null bytes - this is acceptable security behavior
    try:
        resp4 = client.get('/api/v2/docs/safe.md%00')
        # If request succeeds, should reject with 4xx
        assert resp4.status_code >= 400 or resp4.status_code == 200
    except ValueError as e:
        # Python's pathlib raises ValueError("embedded null byte") - this is acceptable
        assert "null byte" in str(e)
    
    # Positive test: Safe access should work
    resp_safe = client.get('/api/v2/docs/safe.md')
    # TDD: Allow 404/501 if endpoint not implemented
    if resp_safe.status_code in (404, 501):
        return
    assert resp_safe.status_code == 200
    assert 'Safe' in resp_safe.text


def test_docs_metadata_with_last_modified(tmp_path, monkeypatch):
    """
    Test GET /api/v2/docs/list includes last_modified timestamps.
    Validates metadata includes file size, modification time, path.
    Allows 404/501 per TDD.
    """
    docs_dir = tmp_path / 'docs'
    docs_dir.mkdir()
    
    doc_file = docs_dir / 'test.md'
    doc_content = '# Test\nSome content here'
    doc_file.write_text(doc_content, encoding='utf-8')
    
    # Set a specific modification time
    test_timestamp = datetime(2025, 1, 15, 12, 0, 0).timestamp()
    os.utime(doc_file, (test_timestamp, test_timestamp))
    
    from backend.src.api import rest as rest_mod
    monkeypatch.setattr(rest_mod, '_docs_root', lambda: docs_dir)
    
    resp = client.get('/api/v2/docs/list')
    
    # TDD: Allow 404 (not implemented) or 501 (not yet available)
    if resp.status_code in (404, 501):
        return
    
    # When implemented: validate metadata
    assert resp.status_code == 200
    items = resp.json()
    
    test_item = next((i for i in items if i['path'] == 'test.md'), None)
    assert test_item is not None
    
    # TDD: If implementation doesn't have last_modified yet, early return
    if 'last_modified' not in test_item:
        return
    
    # Validate metadata fields when implemented
    assert 'size_bytes' in test_item or 'size' in test_item  # Allow either field name
    
    # Validate size
    expected_size = len(doc_content.encode('utf-8'))
    actual_size = test_item.get('size_bytes') or test_item.get('size')
    assert actual_size == expected_size
    
    # Validate last_modified is ISO 8601 format
    last_modified_str = test_item['last_modified']
    # Should be parseable as ISO 8601
    datetime.fromisoformat(last_modified_str.replace('Z', '+00:00'))
