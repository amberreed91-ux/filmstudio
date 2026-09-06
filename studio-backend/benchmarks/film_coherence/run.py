"""Controlled real-provider benchmark. Default is prepare-only, never simulated.

Run from an isolated code checkout with --reference and --output. --execute
requires a configured real provider, current model pricing, and a cost ceiling.
Interrupted/failed rows are never automatically resubmitted.
"""
import argparse
import asyncio
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def atomic_json(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2))
    tmp.replace(path)


def prepare(fixture, reference, output):
    output.mkdir(parents=True, exist_ok=True)
    manifest_path = output / 'manifest.json'
    if manifest_path.exists():
        raise ValueError('This run already exists; automatic resubmission is prohibited')
    reference_copy = output / ('reference' + reference.suffix)
    shutil.copy2(reference, reference_copy)
    manifest = {
        'benchmark_id': fixture['benchmark_id'], 'created_at': datetime.now(timezone.utc).isoformat(),
        'status': 'prepared', 'real_generation_executed': False,
        'reference': str(reference_copy), 'reference_sha256': hashlib.sha256(reference_copy.read_bytes()).hexdigest(),
        'source_context': fixture, 'shots': [], 'review': {'status': 'unreviewed', 'questions': fixture['review_questions']},
    }
    for n, shot in enumerate(fixture['shots']):
        manifest['shots'].append({
            **shot, 'source_context': {'characters': fixture['characters'], 'environment': fixture['environment'], 'continuity': fixture['continuity']},
            'requested_prompt': fixture['anchor_prompt'] + ' ' + shot['direction'],
            'provider': fixture['provider'], 'model': fixture['model'],
            'parameters': {**fixture['parameters'], 'seed': 1400+n},
            'reference_assets': [str(reference_copy)], 'status': 'not_generated',
            'output_asset': None, 'review': [{'expectation': item, 'result': 'not_generated', 'evidence': ''} for item in shot['expectations']],
        })
    atomic_json(manifest_path, manifest)
    return manifest


async def execute(manifest, output, max_cost):
    import requests
    key = os.getenv('OPENROUTER_API_KEY', '')
    if not key:
        manifest['status'] = 'REAL GENERATION BLOCKED'
        manifest['blocker'] = 'OpenRouter credentials unavailable'
        return
    response = requests.get('https://openrouter.ai/api/v1/videos/models', headers={'Authorization': f'Bearer {key}'}, timeout=20)
    response.raise_for_status()
    models = response.json().get('data', [])
    model = next((r for r in models if r.get('id') == manifest['source_context']['model']), None)
    if not model:
        raise ValueError('Configured model is not currently available')
    rate = float((model.get('pricing_skus') or {}).get('duration_seconds_720p', 0))
    estimate = rate * sum(s['parameters']['duration'] for s in manifest['shots'])
    if rate <= 0 or estimate > max_cost:
        raise ValueError('Current model pricing is missing or exceeds cost ceiling')
    manifest['estimated_video_cost_usd'] = estimate
    manifest['video_cost_ceiling_usd'] = max_cost
    manifest['provider_model_snapshot'] = model
    # The priced model and submitted model must be identical even when a shell
    # has an unrelated model override from ordinary studio work.
    os.environ['OPENROUTER_VIDEO_MODEL'] = manifest['source_context']['model']
    from app.data.storage import get_storage
    from app.models import StudioProject
    from app.services.project_store import project_store
    from app.services.render import RenderService, set_storage
    from app.services.prompt_budget_service import validate_provider_text
    storage = get_storage()
    set_storage(storage)
    project_id = 'benchmark-' + output.name
    project = {'project_id': project_id, 'title': manifest['source_context']['title'], 'script_text': '\n'.join(s['direction'] for s in manifest['shots'])}
    project_store.save_project(project)
    storage.save_project(StudioProject(**project))
    for name, description in manifest['source_context']['characters'].items():
        storage.save_character(project_id, name, {'name': name, 'visual_prompt_summary': description})
    reference_dir = ROOT / 'outputs' / 'references'
    reference_dir.mkdir(parents=True, exist_ok=True)
    reference_name = project_id + Path(manifest['reference']).suffix
    shutil.copy2(manifest['reference'], reference_dir / reference_name)
    reference_url = '/outputs/references/' + reference_name
    manifest['registered_reference_url'] = reference_url
    storage.save_reference_asset({'ref_id': 'benchmark-master', 'project_id': project_id, 'kind': 'character_full', 'image_url': reference_url, 'created_at': manifest['created_at']})
    service = RenderService()
    # Preflight every shot BEFORE any paid request.
    jobs = []
    for row in manifest['shots']:
        job = service.create_job(project_id, row['shot_id'], provider=row['provider'], prompt=row['requested_prompt'], parameters=row['parameters'])
        row['job_id'] = job.id
        row['final_generation_prompt'] = job.input_payload.prompt
        row['prompt_budget'] = job.metadata.get('prompt_budget')
        row['status'] = job.status
        row['error'] = job.error_message
        if job.status != 'pending':
            jobs.append(job)
            continue
        validate_provider_text(job, job.input_payload.prompt, row['model'])
        row['consistency_payload'] = (job.input_payload.consistency_payload.model_dump(mode='json') if hasattr(job.input_payload.consistency_payload, 'model_dump') else job.input_payload.consistency_payload)
        from app.adapters import get_adapter
        adapter = get_adapter(row['provider'], service.get_provider_config(row['provider']))
        actual_body = adapter._build_openrouter_body(job, resolution=row['parameters']['resolution'], duration=row['parameters']['duration'], ratio=row['parameters']['ratio'], seed=row['parameters']['seed'])
        if actual_body['model'] != row['model']:
            raise ValueError('Actual provider model differs from the priced benchmark model')
        if not actual_body.get('input_references'):
            raise ValueError('Reference is missing from actual provider request')
        row['provider_request'] = {k: v for k, v in actual_body.items() if k != 'input_references'}
        row['provider_request']['reference_sha256'] = manifest['reference_sha256']
        storage.save_shot_seed(project_id, row['shot_id'], row['parameters']['seed'])
        jobs.append(job)
    manifest['project_id'] = project_id
    if any(job.status != 'pending' for job in jobs):
        raise ValueError('Required reference/identity context exceeds the selected model application prompt budget; review preserved shot evidence')
    atomic_json(output / 'manifest.json', manifest)
    # One submission per shot; record ambiguity instead of retrying paid work.
    for row, job in zip(manifest['shots'], jobs):
        row['status'] = 'submitting'
        atomic_json(output / 'manifest.json', manifest)
        try:
            result = await service.submit_job(job.id)
            row['status'] = result.status
            row['provider_task_id'] = result.provider_job_id
            row['final_generation_prompt'] = (result.metadata or {}).get('final_provider_prompt', result.input_payload.prompt)
            row['provider_payload_metadata'] = (result.metadata or {}).get('provider_payload_metadata')
            row['cost_usd'] = (result.metadata or {}).get('openrouter_cost')
            row['error'] = result.error_message
            manifest['real_generation_executed'] |= bool(result.provider_job_id)
            if result.output_payload and result.output_payload.asset_url:
                local = ROOT / result.output_payload.asset_url.lstrip('/')
                if local.is_file():
                    dest = output / (row['shot_id'] + '.mp4')
                    shutil.copy2(local, dest)
                    row['output_asset'] = str(dest)
                    row['output_sha256'] = hashlib.sha256(dest.read_bytes()).hexdigest()
                    for review in row['review']: review['result'] = 'unclear'
            if result.status != 'complete' or not row['output_asset']:
                manifest['status'] = 'REAL GENERATION BLOCKED'
                manifest['blocker'] = row['error'] or 'Provider did not produce an accessible video'
                break
        except Exception as exc:
            row['provider_task_id'] = job.provider_job_id
            manifest['real_generation_executed'] |= bool(job.provider_job_id)
            row['status'] = 'requires_reconciliation'
            row['error'] = type(exc).__name__
            manifest['status'] = 'REAL GENERATION BLOCKED'
            manifest['blocker'] = 'Submission interrupted; reconcile provider task before any retry'
            break
        finally:
            atomic_json(output / 'manifest.json', manifest)
    else:
        manifest['status'] = 'generated_unreviewed'
    storage.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--max-cost-usd', type=float, default=3.0)
    args = parser.parse_args()
    output = args.output.resolve()
    # Override ALL primary persistence paths before importing application code.
    os.environ['STUDIO_STORAGE_PATH'] = str(output / 'database')
    os.environ['STUDIO_PROJECT_STORE_PATH'] = str(output / 'database' / 'project_state.json')
    os.environ['RENDER_PROVIDER_TEST_MODE'] = 'false'
    os.environ['RENDER_VIDEO_PROVIDER'] = 'openrouter'
    os.environ['PRODUCTION_QUEUE_WORKER_ENABLED'] = 'false'
    os.environ['BACKUP_ENABLED'] = 'false'
    fixture = json.loads((Path(__file__).parent / 'fixture.json').read_text())
    manifest = prepare(fixture, args.reference.resolve(), output)
    try:
        if args.execute:
            asyncio.run(execute(manifest, output, args.max_cost_usd))
    except Exception as exc:
        manifest['status'] = 'REAL GENERATION BLOCKED'
        manifest['blocker'] = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    atomic_json(output / 'manifest.json', manifest)
    print(json.dumps({'status': manifest['status'], 'real_generation_executed': manifest['real_generation_executed'], 'manifest': str(output / 'manifest.json')}))


if __name__ == '__main__':
    main()
