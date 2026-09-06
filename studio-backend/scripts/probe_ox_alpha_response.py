#!/usr/bin/env python3
"""One call to Ox Alpha, printing the ENTIRE response so we can see why content
came back empty. No database access, no writes. Costs one free call.

The staging script got empty content from the model. Empty content on a
reasoning model almost always means one of two things, and this tells us which:
  - finish_reason == "length": the token budget was spent on reasoning before
    any answer was produced. The fix is a much larger max_tokens.
  - the answer is in message.reasoning (or another field), not message.content.
    The fix is to read the right field.

Do not guess between them. Read what this prints.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(BACKEND_ROOT / ".env")
except Exception:
    pass

from openai import OpenAI

api_key = (os.getenv("OPENROUTER_API_KEY") or "").strip()
if not api_key:
    raise SystemExit("OPENROUTER_API_KEY not set in studio-backend/.env")

model = os.getenv("ADHERENCE_VISION_MODEL", "stealth/ox-alpha").strip()
client = OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

# A trivial ask. If this comes back empty too, the problem is the model/params,
# not the length or complexity of the staging prompt.
messages = [
    {"role": "system", "content": "Return strict JSON only. No markdown."},
    {"role": "user", "content": 'Return this exact JSON: {"ok": true, "who": "MAYA"}'},
]

for label, kwargs in [
    ("A: json_object, max_tokens=1200 (what the staging script used)",
     dict(model=model, messages=messages, temperature=0.2, max_tokens=1200,
          response_format={"type": "json_object"})),
    ("B: no response_format, max_tokens=4000",
     dict(model=model, messages=messages, temperature=0.2, max_tokens=4000)),
]:
    print("=" * 72)
    print(label)
    print("=" * 72)
    try:
        resp = client.chat.completions.create(**kwargs)
    except Exception as exc:
        print(f"  call raised: {exc!r}\n")
        continue

    choice = resp.choices[0]
    msg = choice.message
    print("finish_reason :", choice.finish_reason)
    print("content       :", repr(msg.content))
    print("reasoning     :", repr(getattr(msg, "reasoning", None))[:400])
    print("refusal       :", repr(getattr(msg, "refusal", None)))
    if resp.usage:
        u = resp.usage
        print("usage         : prompt=%s completion=%s total=%s" % (
            u.prompt_tokens, u.completion_tokens, u.total_tokens))
        details = getattr(u, "completion_tokens_details", None)
        if details:
            print("  reasoning_tokens:", getattr(details, "reasoning_tokens", None))
    # The full object, in case the useful field is one not named above.
    try:
        print("\nfull message dump:")
        print(json.dumps(msg.model_dump(), indent=2, default=str)[:2000])
    except Exception as exc:
        print("  (could not dump message:", exc, ")")
    print()
