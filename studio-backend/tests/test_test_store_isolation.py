"""Collection must not inherit paths to creator project data."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_conftest_overrides_inherited_developer_store_paths(tmp_path):
    sentinel = tmp_path / 'project_state_store.json'
    original = '{"projects":{"project_3dba9330f43a":{"title":"Do not delete"}}}'
    sentinel.write_text(original)
    env = dict(os.environ, STUDIO_STORAGE_PATH=str(tmp_path), STUDIO_PROJECT_STORE_PATH=str(sentinel))
    code = '''
import conftest, json, os
print('ISOLATION=' + json.dumps({
 'sqlite': os.environ['STUDIO_STORAGE_PATH'],
 'project': str(conftest.project_store._path),
}))
'''
    result = subprocess.run([sys.executable, '-c', code], cwd=Path(__file__).resolve().parents[1], env=env, capture_output=True, text=True, timeout=60, check=True)
    payload = json.loads(next(line.removeprefix('ISOLATION=') for line in result.stdout.splitlines() if line.startswith('ISOLATION=')))
    assert Path(payload['sqlite']) != tmp_path
    assert Path(payload['project']) != sentinel
    assert sentinel.read_text() == original
    assert not (tmp_path / 'studio.db').exists()
