"""Deterministic whole-fact allocation; no trailing-string truncation.

Required facts fit together or generation is stopped before a paid call.
Optional facts are admitted by priority and stable ID, never source position.
Preview/legacy correction helpers retain their old display budgets; the render
service runs them in lossless collection mode and uses this final boundary.
"""
import hashlib
import re

from app.models.prompt_budget import PromptBudgetResult, PromptFact, PromptPriority

ORDER = {value: n for n, value in enumerate(PromptPriority)}
REQUIRED = {PromptPriority.PROVIDER, PromptPriority.IDENTITY, PromptPriority.CONTINUITY, PromptPriority.INTENT}
SLOT_PRIORITY = {
    'character_state': PromptPriority.IDENTITY,
    'identity_continuity': PromptPriority.IDENTITY,
    'action': PromptPriority.INTENT,
    'environment_persistence': PromptPriority.CONTINUITY,
    'lighting': PromptPriority.CONTINUITY,
    'camera': PromptPriority.CINEMATOGRAPHY,
}
FIELD_PRIORITY = {
    'identity': PromptPriority.IDENTITY, 'physical_appearance': PromptPriority.IDENTITY,
    'wardrobe': PromptPriority.CONTINUITY, 'injuries': PromptPriority.CONTINUITY,
    'props': PromptPriority.CONTINUITY, 'location': PromptPriority.CONTINUITY,
    'time_of_day': PromptPriority.CONTINUITY, 'weather': PromptPriority.CONTINUITY,
    'lighting': PromptPriority.CONTINUITY, 'blocking': PromptPriority.CONTINUITY,
    'screen_direction': PromptPriority.CONTINUITY, 'continuity': PromptPriority.CONTINUITY,
    'negative_constraints': PromptPriority.CONTINUITY,
    'story_facts': PromptPriority.INTENT, 'emotional_state': PromptPriority.INTENT,
    'purpose': PromptPriority.INTENT, 'rationale': PromptPriority.INTENT,
    'camera': PromptPriority.CINEMATOGRAPHY, 'lens': PromptPriority.CINEMATOGRAPHY,
    'composition': PromptPriority.CINEMATOGRAPHY, 'movement': PromptPriority.CINEMATOGRAPHY,
    'environment': PromptPriority.ENVIRONMENT, 'enrichment': PromptPriority.ENRICHMENT,
    'optional_detail': PromptPriority.OPTIONAL, 'provider_instructions': PromptPriority.PROVIDER,
}


def prompt_policy(provider, model=''):
    if provider in {'openrouter', 'openrouter-video'} and model == 'alibaba/happyhorse-1.1':
        return 5000, 'Alibaba HappyHorse model ceiling via OpenRouter; OpenRouter schema specifies no additional maximum (transport inference)'
    if provider in {'happyhorse', 'happyhorse-r2v'}:
        return 5000, 'Alibaba HappyHorse API: 5000 non-Chinese / 2500 Chinese characters'
    if model.startswith(('wan2.1', 'wan2.2')):
        return 800, 'Alibaba Wan 2.1/2.2 API: 800 characters'
    if provider == 'wan' or model.startswith(('wan2.5', 'wan2.6')):
        return 1500, 'Alibaba Wan 2.6 API: 1500 characters'
    if provider == 'simulated':
        return 5000, 'Local evaluation policy; does not prove hosted model support'
    # A conservative application ceiling, NOT an asserted vendor maximum.
    # OpenRouter model discovery does not document a universal prompt ceiling.
    return 512, 'Conservative application ceiling; model-specific maximum unverified'


def cost(text, provider, model=''):
    if provider in {'happyhorse', 'happyhorse-r2v'} or (provider in {'openrouter', 'openrouter-video'} and model == 'alibaba/happyhorse-1.1'):
        return sum(2 if '\u3400' <= c <= '\u9fff' or '\U00020000' <= c <= '\U000323af' else 1 for c in text)
    return len(text)


def facts_from_text(text, priority, source):
    # Keep whole sentences/clauses, including negation and actor bindings.
    parts = re.split(r'\n+|(?<=[.!?])\s+', str(text or '').strip())
    facts = []
    for part in parts:
        clean = ' '.join(part.split()).strip()
        if not clean:
            continue
        digest = hashlib.sha256(f'{source}:{clean}'.encode()).hexdigest()[:16]
        facts.append(PromptFact(fact_id=f'{source}:{digest}', text=clean, priority=priority, source=source))
    return facts


def allocate(facts, provider, model='', *, limit=None):
    configured_limit, limit_source = prompt_policy(provider, model)
    if limit is not None:
        configured_limit = min(configured_limit, limit)
        limit_source += '; explicit smaller evaluation budget'
    # Identical statements have their strongest priority. Distinct contradictions
    # are retained for the existing contradiction checker, not silently resolved.
    unique = {}
    for fact in facts:
        key = fact.text.casefold()
        if key not in unique or ORDER[fact.priority] < ORDER[unique[key].priority]:
            unique[key] = fact
    ordered = sorted(unique.values(), key=lambda f: (ORDER[f.priority], f.fact_id))
    required = [f for f in ordered if f.priority in REQUIRED]
    join = lambda rows: ' '.join(f.text for f in rows)
    if cost(join(required), provider, model) > configured_limit:
        return PromptBudgetResult(provider=provider, model=model, limit=configured_limit,
            limit_source=limit_source, prompt='', ready=False,
            required_overflow_ids=[f.fact_id for f in required],
            omitted_ids=[f.fact_id for f in ordered], source_facts=ordered)
    chosen = list(required)
    omitted = []
    for fact in ordered:
        if fact.priority in REQUIRED:
            continue
        if cost(join(chosen + [fact]), provider, model) <= configured_limit:
            chosen.append(fact)
        else:
            omitted.append(fact.fact_id)
    return PromptBudgetResult(provider=provider, model=model, limit=configured_limit,
        limit_source=limit_source, prompt=join(chosen), included_ids=[f.fact_id for f in chosen],
        omitted_ids=omitted, source_facts=ordered)


def budget_job(job):
    params = job.input_payload.parameters or {}
    slots = params.get('prompt_slots') or {}
    facts = []
    for name, text in slots.items():
        if name in SLOT_PRIORITY and text:
            facts += facts_from_text(text, SLOT_PRIORITY[name], name)
    raw_prompt = job.input_payload.prompt or ''
    if facts:
        # Add prose introduced after slot construction (intent and continuity).
        # Extract known slot text before classifying the remainder.
        remainder = raw_prompt
        for text in sorted((str(v) for v in slots.values() if v), key=len, reverse=True):
            remainder = remainder.replace(text, '')
        remainder = remainder.replace('Cinematic, film quality.', '').strip(' .;\n')
        if remainder:
            facts += facts_from_text(remainder, PromptPriority.CONTINUITY, 'post_slot_context')
    else:
        # Unstructured creator text cannot safely be declared optional by guessing.
        facts += facts_from_text(raw_prompt, PromptPriority.INTENT, 'creator_prompt')
    for field, value in (params.get('shot_planning') or {}).items():
        if field in FIELD_PRIORITY and value:
            facts += facts_from_text(value, FIELD_PRIORITY[field], 'shot_planning.' + field)
    for item in params.get('prompt_facts') or []:
        facts.append(PromptFact.model_validate(item))
    from app.services.render import _provider_model_for_job
    result = allocate(facts, job.provider, _provider_model_for_job(job.provider, params))
    # Preserve the filmmaker's sequence and context delimiters when no
    # degradation is necessary. Priority controls admission, not needless
    # rearrangement of a valid short prompt (retry delimiters are significant).
    if result.ready and not result.omitted_ids and cost(raw_prompt, job.provider, result.model) <= result.limit and all(f.text in raw_prompt for f in result.source_facts):
        result.prompt = raw_prompt
    negative = budget_negative(job)
    if not negative['ready']:
        result.ready = False
        result.required_overflow_ids += ['negative_constraints']
    job.metadata = dict(job.metadata or {})
    job.metadata['negative_prompt_budget'] = negative
    job.metadata['prompt_budget'] = result.model_dump(mode='json')
    params['prompt_budget'] = result.model_dump(mode='json')
    job.input_payload.parameters = params
    if result.ready:
        job.input_payload.prompt = result.prompt
    else:
        # Preserve the unabridged text for review; submit_job rejects needs_review.
        job.status = 'needs_review'
        job.error_message = 'Required shot facts exceed this provider’s prompt budget. Shorten the required context or choose a provider with a verified larger budget.'
    return result


def validate_provider_text(job, text, model=''):
    limit, source = prompt_policy(job.provider, model)
    if cost(text, job.provider, model) > limit:
        raise ValueError(f'Provider prompt exceeds {limit} character units after reference adaptation ({source}); no request submitted')
    job.metadata = dict(job.metadata or {})
    job.metadata['final_provider_prompt'] = text
    job.metadata['final_provider_prompt_policy'] = {'limit': limit, 'source': source, 'model': model}


def budget_negative(job):
    """Preserve explicit exclusions; degrade only generated defaults, whole term."""
    from app.services.negative_prompt_builder import provider_supports_negative_prompt
    params = job.input_payload.parameters or {}
    required = list(dict.fromkeys(str(x).strip() for x in (params.get('required_negative_terms') or params.get('negative_prompt_terms') or []) if str(x).strip()))
    supported = provider_supports_negative_prompt(job.provider)
    # Conservative separate-channel ceiling, matching the existing application
    # policy. Never infer positive-channel capacity for a negative channel.
    limit = 500
    original = job.input_payload.negative_prompt or ''
    report = {'limit': limit, 'supported': supported, 'required_terms': required, 'source_text': original, 'omitted_terms': [], 'ready': True}
    if required and (not supported or len(', '.join(required)) > limit):
        report['ready'] = False
        report['reason'] = 'Explicit exclusions unsupported or exceed separate negative-channel budget'
        return report
    chosen = list(required)
    for term in original.split(', '):
        if not term or term in chosen:
            continue
        if len(', '.join(chosen + [term])) <= limit:
            chosen.append(term)
        else:
            report['omitted_terms'].append(term)
    job.input_payload.negative_prompt = ', '.join(chosen)
    report['final_text'] = job.input_payload.negative_prompt
    return report
