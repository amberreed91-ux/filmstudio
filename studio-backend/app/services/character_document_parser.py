"""Deterministic import of categorized cast manifests and heading-based bibles."""
from __future__ import annotations

import json
import re
from io import BytesIO
from xml.etree import ElementTree as ET
from zipfile import ZipFile

CATEGORIES = ('principal', 'supporting', 'recurring', 'featured', 'day_players')
LABELS = {
    'Category': 'category', 'Age / timeline': 'age_timeline', 'Story function': 'story_function',
    'Appearance / visual lock': 'appearance', 'Wardrobe': 'wardrobe',
    'Personality / behavior': 'personality', 'Voice / dialogue': 'voice_direction',
    'Key relationships': 'relationships', 'Arc': 'arc', 'Continuity locks': 'continuity_notes',
    'Image generation prompt': 'image_prompt',
}


def parse_character_document(filename: str, contents: bytes) -> dict | None:
    if filename.lower().endswith('.json'):
        document = json.loads(contents.decode('utf-8-sig'))
        if not isinstance(document, dict) or not any(key in document for key in CATEGORIES):
            return None
        profiles = []
        for category in CATEGORIES:
            rows = document.get(category, [])
            if not isinstance(rows, list):
                raise ValueError(f'{category} must be a list.')
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get('script_name'), str) or not row['script_name'].strip():
                    raise ValueError('Each cast entry needs a script_name.')
                if any(not isinstance(value, str) for value in row.values()):
                    raise ValueError('Cast entry fields must be text.')
                profiles.append({'name': row['script_name'], **row, 'category': category,
                                 'story_function': row.get('function') or row.get('scene_function', '')})
        return {'kind': 'cast_manifest', 'profiles': profiles, 'context': {key: value for key, value in document.items() if key not in CATEGORIES}}
    if not filename.lower().endswith('.docx'):
        return None
    with ZipFile(BytesIO(contents)) as archive:
        info = archive.getinfo('word/document.xml')
        if info.file_size > 8 * 1024 * 1024:
            raise ValueError('The document is too large to import.')
        root = ET.fromstring(archive.read(info))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
    profiles, general = [], []
    current = None
    for paragraph in root.findall('.//w:p', ns):
        text = ''.join(paragraph.itertext()).strip()
        if not text:
            continue
        style = paragraph.find('./w:pPr/w:pStyle', ns)
        heading = style.get('{'+ns['w']+'}val', '').lower() if style is not None else ''
        if heading == 'heading2':
            current = {'name': text}
            profiles.append(current)
        elif heading == 'heading1':
            current = None
            general.append(text)
        elif current is None:
            general.append(text)
        else:
            label, separator, value = text.partition(':')
            field = LABELS.get(label.strip()) if separator else None
            if field:
                current[field] = value.strip()
            else:
                current.setdefault('additional_notes', '')
                current['additional_notes'] += ('\n' if current['additional_notes'] else '') + text
    if not profiles or not any('appearance' in row or 'story_function' in row for row in profiles):
        return None
    return {'kind': 'character_bible', 'profiles': profiles, 'context': {'general_notes': '\n'.join(general)}}


def identity_tokens(name: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", name.casefold()))
    return tokens - {'dr', 'mr', 'mrs', 'ms', 'lieutenant', 'commander', 'reverend', 'unc', 'uncle'}


def match_document_name(name: str, candidates: list[dict]) -> dict | None:
    exact = [row for row in candidates if row['name'].casefold() == name.casefold()]
    if exact:
        return exact[0]
    tokens = identity_tokens(name)
    kinship = tokens & {'mother', 'father', 'daughter', 'son', 'cousin', 'girlfriend'}
    matches = [row for row in candidates if tokens and
               (not kinship or kinship <= identity_tokens(row['name'])) and
               (tokens <= identity_tokens(row['name']) or identity_tokens(row['name']) <= tokens)]
    if not matches:
        return None
    best = max(len(identity_tokens(row['name']) & tokens) for row in matches)
    matches = [row for row in matches if len(identity_tokens(row['name']) & tokens) == best]
    return matches[0] if len(matches) == 1 else None
