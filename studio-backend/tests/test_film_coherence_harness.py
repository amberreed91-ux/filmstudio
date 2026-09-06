import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('coherence_harness', ROOT / 'benchmarks/film_coherence/run.py')
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)


def test_prepare_is_explicitly_not_generated_and_cannot_overwrite(tmp_path):
    fixture = json.loads((ROOT / 'benchmarks/film_coherence/fixture.json').read_text())
    reference = tmp_path / 'fixture.png'
    reference.write_bytes(b'test reference bytes; no generation')
    output = tmp_path / 'run'
    result = harness.prepare(fixture, reference, output)
    assert not result['real_generation_executed']
    assert len(result['shots']) == 6
    assert all(s['status'] == 'not_generated' and s['output_asset'] is None for s in result['shots'])
    assert all(s['provider'] != 'simulated' and s['source_context'] and s['reference_assets'] and s['parameters'] and s['expectations'] for s in result['shots'])
    with pytest.raises(ValueError, match='resubmission'):
        harness.prepare(fixture, reference, output)


@pytest.mark.asyncio
async def test_missing_credentials_mark_blocked_without_fake_output(tmp_path, monkeypatch):
    monkeypatch.delenv('OPENROUTER_API_KEY', raising=False)
    result = {'real_generation_executed': False}
    await harness.execute(result, tmp_path, 3)
    assert result['status'] == 'REAL GENERATION BLOCKED'
    assert not result['real_generation_executed']
