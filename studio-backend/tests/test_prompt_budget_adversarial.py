from itertools import permutations
from unittest.mock import AsyncMock

import pytest

from app.models import RenderJobModel, RenderJobInput
from app.models.prompt_budget import PromptFact, PromptPriority
from app.services.prompt_budget_service import allocate, budget_job, cost, facts_from_text, FIELD_PRIORITY, validate_provider_text
from app.prompt_assembly_context import preserve_generation_facts
from app.services.shot_prompt_builder import build_slotted_prompt


def fact(name, priority, text=None):
    return PromptFact(fact_id=name, priority=priority, text=text or name, source='adversarial')


def test_priority_is_independent_of_input_order_and_never_clips_negation():
    facts = [fact('identity', PromptPriority.IDENTITY, 'Maya has brown eyes.'),
             fact('continuity', PromptPriority.CONTINUITY, 'The bandage stays on her left wrist.'),
             fact('optional', PromptPriority.OPTIONAL, 'Decorative textures shimmer across every distant wall.'),
             fact('provider', PromptPriority.PROVIDER, 'Do not cross the established axis.')]
    results = [allocate(list(order), 'happyhorse', limit=115) for order in permutations(facts)]
    assert len({r.prompt for r in results}) == 1
    assert all(r.ready and r.included_ids == ['provider', 'identity', 'continuity'] and r.omitted_ids == ['optional'] for r in results)
    assert 'Do not cross the established axis.' in results[0].prompt


def test_required_overflow_blocks_instead_of_losing_identity():
    result = allocate([fact('identity', PromptPriority.IDENTITY, 'Very long immutable identity. ' * 200)], 'happyhorse', limit=50)
    assert not result.ready
    assert result.prompt == ''
    assert result.required_overflow_ids == ['identity']


@pytest.mark.parametrize('field', list(FIELD_PRIORITY))
def test_every_filmmaking_field_survives_before_optional_enrichment(field):
    important = fact(field, FIELD_PRIORITY[field], f'{field}: KEEP_{field}.')
    enrichment = fact('huge', PromptPriority.OPTIONAL, 'Decorative background texture ' * 500)
    result = allocate([enrichment, important], 'happyhorse')
    assert result.ready
    assert f'KEEP_{field}' in result.prompt
    assert 'huge' in result.omitted_ids


def test_chinese_character_budget_and_whole_fact_boundary():
    required = fact('identity', PromptPriority.IDENTITY, '人物' * 1200)
    assert cost(required.text, 'happyhorse') == 4800
    result = allocate([required, fact('optional', PromptPriority.OPTIONAL, '夜晚' * 100)], 'happyhorse')
    assert result.ready and result.prompt == required.text
    assert result.omitted_ids == ['optional']


def test_generation_collection_retains_lighting_and_wardrobe_beyond_legacy_cut():
    args = dict(scene_data={}, shot_number=1, character_visual_canon='MAYA wears a red coat. ' + 'Her face has freckles. ' * 8,
                action_text='Maya holds the brass key. ' * 4, environment_motifs='The workshop has green tile walls. ' * 3,
                camera_direction='A 50mm lens remains south of the table. ' * 2, lighting_direction='LIGHTING_SENTINEL: amber desk lamp, no daylight.')
    before = build_slotted_prompt(**args)
    after = preserve_generation_facts(build_slotted_prompt)(**args)
    assert 'LIGHTING_SENTINEL' not in before['prompt']
    job = RenderJobModel(id='p', project_id='p', shot_id='s', provider='happyhorse', input_payload=RenderJobInput(prompt=after['prompt'], parameters={'prompt_slots': after['slots']}))
    result = budget_job(job)
    assert result.ready
    assert 'LIGHTING_SENTINEL' in job.input_payload.prompt
    assert 'red coat' in job.input_payload.prompt
    assert 'brass key' in job.input_payload.prompt
    assert 'green tile' in job.input_payload.prompt
    assert len(job.input_payload.prompt) <= 5000


def test_unstructured_oversize_prompt_is_preserved_for_review():
    raw = 'Keep Maya unchanged. ' * 300
    job = RenderJobModel(id='p', project_id='p', shot_id='s', provider='runway', input_payload=RenderJobInput(prompt=raw))
    # Distinct required facts must exceed the budget; exact repeats are deduped.
    job.input_payload.prompt = '\n'.join(f'Prop {n} must stay in its place.' for n in range(100))
    original = job.input_payload.prompt
    assert not budget_job(job).ready
    assert job.status == 'needs_review'
    assert job.input_payload.prompt == original


def test_adapter_additions_cannot_bypass_final_budget():
    job = RenderJobModel(id='p', project_id='p', shot_id='s', provider='happyhorse')
    with pytest.raises(ValueError, match='after reference adaptation'):
        validate_provider_text(job, 'x' * 5001, 'happyhorse-1.1-t2v')


def test_required_negative_exclusions_survive_default_terms():
    from app.services.prompt_budget_service import budget_negative
    job = RenderJobModel(id='n', project_id='p', shot_id='s', provider='happyhorse', input_payload=RenderJobInput(negative_prompt=', '.join('default artifact '+str(i) for i in range(100)), parameters={'negative_prompt_terms': ['rain', 'missing left wrist bandage']}))
    report = budget_negative(job)
    assert report['ready']
    assert job.input_payload.negative_prompt.startswith('rain, missing left wrist bandage')
    assert len(job.input_payload.negative_prompt) <= 500
    assert report['omitted_terms']


def test_unsupported_explicit_negatives_block_paid_generation():
    job = RenderJobModel(id='n', project_id='p', shot_id='s', provider='openrouter', input_payload=RenderJobInput(prompt='Maya waits.', parameters={'negative_prompt_terms': ['rain']}))
    assert not budget_job(job).ready
    assert job.status == 'needs_review'
    assert job.metadata['negative_prompt_budget']['required_terms'] == ['rain']


def test_oversize_required_negative_clause_is_never_cut():
    from app.services.prompt_budget_service import budget_negative
    required = 'continuity exclusion ' * 80
    job = RenderJobModel(id='n', project_id='p', shot_id='s', provider='happyhorse', input_payload=RenderJobInput(parameters={'negative_prompt_terms': [required]}))
    result = budget_negative(job)
    assert not result['ready']
    assert result['required_terms'] == [required.strip()]


def test_review_blocked_job_and_budget_evidence_survive_sqlite_reload(tmp_path):
    from app.data.storage import DatabaseStorage
    storage = DatabaseStorage(str(tmp_path))
    job = RenderJobModel(id='blocked', project_id='p', shot_id='s', provider='runway', input_payload=RenderJobInput(prompt=' '.join(f'Immutable continuity fact {n}.' for n in range(100))))
    result = budget_job(job)
    assert not result.ready
    storage.save_job(job)
    restored = storage.get_job(job.id)
    assert restored.status == 'needs_review'
    assert restored.input_payload.prompt == job.input_payload.prompt
    assert restored.metadata['prompt_budget'] == job.metadata['prompt_budget']
    assert restored.metadata['negative_prompt_budget'] == job.metadata['negative_prompt_budget']
    storage.close()


def test_review_migration_preserves_existing_jobs_and_indexes(tmp_path):
    from app.data.storage import DatabaseStorage
    store = DatabaseStorage(str(tmp_path))
    job = RenderJobModel(id='prior', project_id='p', shot_id='s', provider='runway', status='complete', provider_job_id='provider-prior')
    store.save_job(job)
    with store._get_connection() as conn:
        conn.execute('ALTER TABLE render_jobs DROP COLUMN metadata_json')
        conn.execute('DELETE FROM schema_migrations WHERE version = 61')
        conn.commit()
    store.close()
    migrated = DatabaseStorage(str(tmp_path))
    assert migrated.get_job('prior').provider_job_id == 'provider-prior'
    assert migrated.get_job('prior').status == 'complete'
    with migrated._get_connection() as conn:
        indexes = {row[1] for row in conn.execute('PRAGMA index_list(render_jobs)')}
    assert {'idx_render_jobs_project', 'idx_render_jobs_status', 'idx_render_jobs_created', 'idx_render_jobs_provider'} <= indexes
    migrated.close()


def test_openrouter_happyhorse_budget_uses_actual_model_and_unknowns_stay_conservative():
    from app.services.prompt_budget_service import prompt_policy
    assert prompt_policy('openrouter', 'alibaba/happyhorse-1.1')[0] == 5000
    assert prompt_policy('openrouter', 'unknown/model')[0] == 512
    assert cost('人物', 'openrouter', 'alibaba/happyhorse-1.1') == 4
    job = RenderJobModel(id='model', project_id='p', shot_id='s', provider='openrouter', input_payload=RenderJobInput(prompt=' '.join(f'Keep immutable fact {n}.' for n in range(35))))
    result = budget_job(job)
    assert result.ready and result.model == 'alibaba/happyhorse-1.1'
    assert len(result.prompt) > 512
