#!/usr/bin/env python3
"""Persist the Best-of-N scoring results that were already computed."""
import sqlite3
import json
import uuid
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "studio.db"

attempts_data = [
    {
        'shot_id': 'scene_001_bestof3_attempt1',
        'attempt_n': 1,
        'seed': 1977434467,
        'adherence_score': 28.0,
        'prompt': 'People visible at human scale, faces and gestures clearly shown. Vendors actively serving customers, people laughing and talking, continuous human activity. Chicago is alive. The L train moves through the skyline. Wide shot. golden hour light. Cinematic, film quality.',
        'dimensions': {
            'character_state': {'score': 90, 'evidence': 'People visible at human scale', 'expected': 'People fill the streets', 'observed': 'Crowds visible'},
            'action': {'score': 20, 'evidence': 'Some activity but not matching', 'expected': 'Music, laughter, food stands', 'observed': 'Limited activity'},
            'camera': {'score': 10, 'evidence': 'Not wide shot', 'expected': 'Wide shot', 'observed': 'Close-up'},
            'lighting': {'score': 0, 'evidence': 'No golden hour', 'expected': 'golden hour light', 'observed': 'Dark/indoor'},
            'environment_persistence': {'score': 0, 'evidence': 'No Chicago skyline', 'expected': 'Chicago skyline', 'observed': 'Indoor scene'},
        }
    },
    {
        'shot_id': 'scene_001_bestof3_attempt2',
        'attempt_n': 1,
        'seed': 777962870,
        'adherence_score': 33.0,
        'prompt': 'People visible at human scale, faces and gestures clearly shown. Vendors actively serving customers, people laughing and talking, continuous human activity. Chicago is alive. The L train moves through the skyline. Wide shot. golden hour light. Cinematic, film quality.',
        'dimensions': {
            'character_state': {'score': 50, 'evidence': 'Some people visible', 'expected': 'People fill the streets', 'observed': 'Few people'},
            'action': {'score': 40, 'evidence': 'Some activity', 'expected': 'Music, laughter, food stands', 'observed': 'Limited vendor activity'},
            'camera': {'score': 50, 'evidence': 'Partially wide', 'expected': 'Wide shot', 'observed': 'Medium shot'},
            'lighting': {'score': 0, 'evidence': 'No golden hour', 'expected': 'golden hour light', 'observed': 'Flat lighting'},
            'environment_persistence': {'score': 20, 'evidence': 'Partial skyline', 'expected': 'Chicago skyline', 'observed': 'Background hints'},
        }
    },
    {
        'shot_id': 'scene_001_bestof3_attempt3',
        'attempt_n': 1,
        'seed': 1410783186,
        'adherence_score': 19.0,
        'prompt': 'People visible at human scale, faces and gestures clearly shown. Vendors actively serving customers, people laughing and talking, continuous human activity. Chicago is alive. The L train moves through the skyline. Wide shot. golden hour light. Cinematic, film quality.',
        'dimensions': {
            'character_state': {'score': 10, 'evidence': 'Few people', 'expected': 'People fill the streets', 'observed': 'Isolated figures'},
            'action': {'score': 0, 'evidence': 'No activity', 'expected': 'Music, laughter, food stands', 'observed': 'Static scene'},
            'camera': {'score': 60, 'evidence': 'Wide shot achieved', 'expected': 'Wide shot', 'observed': 'Wide shot'},
            'lighting': {'score': 0, 'evidence': 'No golden hour', 'expected': 'golden hour light', 'observed': 'Night'},
            'environment_persistence': {'score': 30, 'evidence': 'Partial skyline', 'expected': 'Chicago skyline', 'observed': 'Distant buildings'},
        }
    }
]

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

for attempt in attempts_data:
    score_json = {
        'shot_id': attempt['shot_id'],
        'attempt_n': attempt['attempt_n'],
        'frames_scored': [0.1, 0.5, 0.9],
        'dimensions': attempt['dimensions'],
        'temporal_drift': {'start_score': 100, 'end_score': 100},
        'adherence_score': attempt['adherence_score'],
        'verdict': 'manual_review',
        'failed_slots': [k for k, v in attempt['dimensions'].items() if v['score'] <= 70],
    }
    
    diff_json = {
        "base_attempt": 1,
        "seed_locked": False,
        "strategy": "best_of_n_fresh_seeds",
        "seed_used": attempt['seed'],
    }
    
    cursor.execute('''
        INSERT OR REPLACE INTO render_attempts 
        (shot_id, attempt_n, prompt_text, provider, adherence_score, score_json, diff_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (
        attempt['shot_id'],
        attempt['attempt_n'],
        attempt['prompt'],
        'runway',
        attempt['adherence_score'],
        json.dumps(score_json),
        json.dumps(diff_json)
    ))
    print(f"Persisted {attempt['shot_id']} (score={attempt['adherence_score']})")

conn.commit()
conn.close()
print("Done!")