#!/usr/bin/env python3
"""Live reference-continuity validation driver — Part 2/3/6/7 of the workstream.

Runs against the ISOLATED backend (port 8047, own DB in studio-backend/.validation).

Flow (all through sanctioned Studio paths — no shortcuts around approval):
  1. Auth + controlled project
  2. Scene 1 "Environment Scout" (no characters) → t2v render via local LTX
     → ffmpeg first frame → canonical environment reference registered via the
     two-phase propose/confirm promotion (the only live ReferenceAsset path)
  3. Character "Maya" + canonical look locked through the look upload workflow
  4. Supporting references — file upload AND real http URL ingestion —
     candidate → approve; plus candidate-only and rejected-only rows
  5. Fail-closed probes (candidate-only, wrong-character, invalid image)
  6. Scene 2 + Scene 3 renders (same character/setting, different context)
"""
from __future__ import annotations

import io
import json
import subprocess
import sys
import time
from pathlib import Path

import httpx
from PIL import Image

BASE = "http://127.0.0.1:8047"
URL_BASE = "http://127.0.0.1:8055"  # tiny static server for genuine URL refs
LOCATION = "brick-loft-interior"  # pre-normalized: scene.location must equal the setting target id
SHOT_SCOUT = "scene_001_shot_001"
SHOT_S1 = "scene_002_shot_001"
SHOT_S2 = "scene_003_shot_001"
REF_DIR = Path(__file__).resolve().parents[1] / ".validation" / "url_refs"

# Resolution steering: the local LTX panel OOM-kills (jetsam) at the 768x448
# default on this 16 GB host under memory pressure, while 512x320 completed
# repeatedly on 2026-09-20/21. The adapter accepts width/height through job
# parameters (translate_studio_request), so every render below pins the smaller
# tier. frames=49 (49 % 8 == 1, ~3 s @ 24 fps) shrinks the denoise activation
# footprint ~2.5x versus 121 frames to fit the currently wired/pressured
# memory state. steps 8, quality balanced — all verified adapter values.
RESOLUTION_PARAMS = {"width": 512, "height": 320, "frames": 49}

results: list[tuple[str, str, str]] = []


def record(step: str, status: str, detail: str = "") -> None:
    results.append((step, status, detail))
    print(f"[{status:9s}] {step}" + (f" — {detail}" if detail else ""), flush=True)


def make_reference_image(label: str, size: tuple[int, int]) -> bytes:
    import math

    width, height = size
    palette = {
        "maya-face": (168, 108, 74), "maya-full": (196, 138, 96),
        "maya-wardrobe": (88, 102, 70), "maya-night": (60, 66, 92), "maya-extra": (120, 84, 60),
        "maya-candidate": (210, 180, 140), "maya-rejected": (96, 48, 48),
        "loft-night": (52, 48, 66), "loft-detail": (188, 168, 140),
    }
    r0, g0, b0 = palette.get(label, (100, 100, 100))
    image = Image.new("RGB", (width, height))
    pixels = image.load()
    for y in range(height):
        for x in range(width):
            w = math.sin((x / width) * math.pi)
            t = y / height
            pixels[x, y] = (
                min(255, int(r0 * (0.55 + 0.5 * w) * (1.05 - 0.25 * t))),
                min(255, int(g0 * (0.55 + 0.5 * w) * (1.05 - 0.25 * t))),
                min(255, int(b0 * (0.55 + 0.5 * w) * (1.05 - 0.25 * t))),
            )
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


client = httpx.Client(timeout=90.0)

# ══ 1. Auth + project ════════════════════════════════════════════════════
response = client.post(f"{BASE}/api/f51/studio/auth/login", json={"username": "valadmin", "password": "ValidationPass123!"})
if response.status_code != 200:
    response = client.post(f"{BASE}/api/f51/studio/auth/register", json={"username": "valadmin", "email": "val@studio.local", "password": "ValidationPass123!"})
response.raise_for_status()
data = response.json()
session_id = data.get("session_id") or (data.get("session") or {}).get("session_id") if isinstance(data.get("session"), dict) else data.get("session_id")
session_id = session_id or client.cookies.get("session_id")
assert session_id, f"no session: {data}"
client.headers.update({"Authorization": f"Bearer {session_id}"})
record("auth", "OK")

response = client.post(f"{BASE}/api/f51/studio/projects", json={"title": "VAL Reference Continuity"})
assert response.status_code in (200, 201), response.text
PROJECT_ID = response.json().get("project_id") or response.json().get("id")
assert PROJECT_ID, response.text[:300]
OUT_DIR = Path(__file__).resolve().parents[1] / "outputs" / "previs" / PROJECT_ID
record("create_project", "OK", PROJECT_ID)

LIB = f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/reference-library"


SCENE_IDS: list[str] = []


def create_scene(scene_name: str, description: str, characters: list[str]) -> str:
    response = client.post(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/scenes",
                           json={"scene_name": scene_name, "description": description, "location": LOCATION,
                                 "time_of_day": "DAY", "characters": characters})
    assert response.status_code == 200, response.text
    scene = response.json().get("scene") or response.json()
    scene_id = str(scene.get("scene_id") or "")
    SCENE_IDS.append(scene_id)
    return scene_id


def pin_setting_id_on_scenes() -> None:
    """Give each scene an explicit location_id equal to the setting target id.

    Scenes created through the scenes API store ``location`` as a display
    string; reference_validation._setting_id() only matches the canonical
    environment reference (target_id=LOCATION) when the scene record carries
    ``location_id`` (or setting_id/environment_id). The environment continuity
    service reads the same field, so both layers resolve the same setting id.
    Done through the sanctioned project-update endpoint in one write.
    """
    response = client.get(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}")
    assert response.status_code == 200, response.text
    project = response.json()
    summary = project.get("execution_summary") or {}
    scenes = summary.get("scenes") or []
    changed = False
    for scene in scenes:
        if isinstance(scene, dict) and not str(scene.get("location_id") or "").strip():
            scene["location_id"] = LOCATION
            changed = True
    if changed:
        updated = client.put(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}",
                             json={"execution_summary": summary})
        assert updated.status_code == 200, updated.text
    record("scenes_pinned_to_setting", "OK", f"location_id={LOCATION} scenes={len(scenes)}")


# ══ 2. Scout scene + environment scout render (t2v, no characters) ═══════
scout_scene = create_scene("Environment Scout", "Empty brick loft interior establishing plate.", [])
record("scene_001_scout", "OK", scout_scene)

response = client.post(
    f"{BASE}/api/f51/studio/render/jobs",
    params={
        "project_id": PROJECT_ID, "shot_id": SHOT_SCOUT, "provider": "local_ltx",
        "prompt": "Empty sunlit brick loft interior, tall industrial windows, worn wooden floors, dust motes in light shafts. Slow push-in, anamorphic, natural grade.",
        "parameters": json.dumps(RESOLUTION_PARAMS),
    },
)
assert response.status_code == 200, response.text
scout_job_id = response.json()["job_id"]
submit = client.post(f"{BASE}/api/f51/studio/render/jobs/{scout_job_id}/submit")
assert submit.status_code == 200, submit.text
record("scout_submit", "OK", f"job={scout_job_id} status={submit.json().get('status')}")

scout_url = ""
for _ in range(60):
    time.sleep(10)
    status = client.get(f"{BASE}/api/f51/studio/render/jobs/{scout_job_id}/status").json()
    state = status.get("status")
    if state in ("complete", "failed", "cancelled"):
        if state == "complete":
            scout_url = status.get("output_url") or (status.get("output_payload") or {}).get("asset_url") or ""
        break
    print(f"    scout: {state} {status.get('progress')}%", flush=True)
assert scout_url, "scout render did not complete"
record("scout_complete", "OK", scout_url[:90])

OUT_DIR.mkdir(parents=True, exist_ok=True)
env_still = OUT_DIR / "scene_001_env_still.jpg"
probe = subprocess.run(["ffmpeg", "-i", scout_url, "-vframes", "1", "-q:v", "2", "-y", str(env_still)], capture_output=True, timeout=60)
assert probe.returncode == 0 and env_still.exists(), probe.stderr.decode()[-300:]
record("env_still_extracted", "OK", f"{env_still.stat().st_size} bytes")

env_url = f"/previs-assets/{PROJECT_ID}/scene_001_env_still.jpg"
confirm_payload = {
    "ref_id": "proposal_env_canonical_001", "kind": "environment", "image_url": env_url,
    "source_shot_id": SHOT_SCOUT, "project_id": PROJECT_ID,
    "target_type": "setting", "target_id": LOCATION, "category": "canonical",
    "approval_state": "approved", "canonical": True, "source_kind": "confirmed",
}
confirmed = client.post(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/reference-assets", json=confirm_payload)
assert confirmed.status_code == 200, confirmed.text
record("canonical_env_registered", "OK", confirmed.json()["reference_asset"]["ref_id"])

# ══ 3. Identity scenes + character + canonical look (uploads) ════════════
create_scene("Morning Establishing", "Maya crosses the loft at dawn carrying a crumpled letter.", ["Maya"])
create_scene("Night Window", "Maya stands at the loft window at night, city glow on her face.", ["Maya"])
record("scenes_002_003", "OK")
pin_setting_id_on_scenes()

response = client.post(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/characters", json={"name": "Maya"})
response.raise_for_status()
CHARACTER_ID = response.json()["character"]["id"]
record("create_character", "OK", CHARACTER_ID)

client.put(
    f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/characters/{CHARACTER_ID}",
    json={"look": "Late 20s. Lean build, deep brown skin, dark still eyes, natural locs; practical layered neutrals, canvas jacket."},
).raise_for_status()
face_url = client.post(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/characters/{CHARACTER_ID}/look/reference",
                       files={"file": ("maya-face.jpg", make_reference_image("maya-face", (640, 960)), "image/jpeg")}).json()["image_url"]
body_url = client.post(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/characters/{CHARACTER_ID}/look/reference",
                       files={"file": ("maya-full.jpg", make_reference_image("maya-full", (768, 1024)), "image/jpeg")}).json()["image_url"]
look = client.get(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/characters/{CHARACTER_ID}/look").json()
approved = client.post(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/characters/{CHARACTER_ID}/look/approve",
                       json={"expected_profile_revision": look["profile_revision"], "face_image_url": face_url, "body_image_url": body_url})
assert approved.status_code == 200, approved.text
record("canonical_look_approved", "OK", f"face={face_url}")

# ══ 4. Supporting references: upload + genuine URL ingestion ═════════════
REF_DIR.mkdir(parents=True, exist_ok=True)
for name, label, size in [("maya-wardrobe.jpg", "maya-wardrobe", (640, 960)), ("maya-night.jpg", "maya-night", (640, 960)), ("maya-extra.jpg", "maya-extra", (640, 960)), ("loft-detail.jpg", "loft-detail", (1024, 640))]:
    (REF_DIR / name).write_bytes(make_reference_image(label, size))
static_server = subprocess.Popen(["python3", "-m", "http.server", "8055", "--bind", "127.0.0.1", "--directory", str(REF_DIR)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(1.5)
record("url_ref_server", "OK", URL_BASE)

uploaded_char = client.post(f"{LIB}/character/{CHARACTER_ID}/upload",
                            files={"file": ("maya-profile.jpg", make_reference_image("maya-profile", (640, 960)), "image/jpeg")},
                            data={"category": "profile"}).json()["reference_asset"]
record("char_upload", "OK", f"{uploaded_char['ref_id']} state={uploaded_char['approval_state']} src={uploaded_char['source_kind']} trace={uploaded_char['source_shot_id']}")

url_char_refs = {}
for name, category in [("maya-wardrobe", "wardrobe"), ("maya-night", "night"), ("maya-extra", "expression")]:
    row = {"ref_id": f"ref_{name}", "kind": "character_full", "image_url": f"{URL_BASE}/{name}.jpg",
           "category": category, "approval_state": "candidate", "source_kind": "uploaded", "source_shot_id": "reference-url",
           "target_type": "character", "target_id": CHARACTER_ID, "project_id": PROJECT_ID}
    added = client.post(f"{LIB}/character/{CHARACTER_ID}", json=row)
    assert added.status_code == 200, added.text
    url_char_refs[name] = added.json()

uploaded_setting = client.post(f"{LIB}/setting/{LOCATION}/upload",
                               files={"file": ("loft-night.jpg", make_reference_image("loft-night", (1024, 640)), "image/jpeg")},
                               data={"category": "night"}).json()["reference_asset"]
row = {"ref_id": "ref_loft-detail-url", "kind": "environment", "image_url": f"{URL_BASE}/loft-detail.jpg",
       "category": "detail", "approval_state": "candidate", "source_kind": "uploaded", "source_shot_id": "reference-url",
       "target_type": "setting", "target_id": LOCATION, "project_id": PROJECT_ID}
url_setting_ref = client.post(f"{LIB}/setting/{LOCATION}", json=row).json()
record("supporting_registered", "OK", f"uploads={uploaded_char['ref_id']},{uploaded_setting['ref_id']} urls={list(url_char_refs) + [url_setting_ref['ref_id']]}")

CAND = client.post(f"{LIB}/character/{CHARACTER_ID}/upload",
                   files={"file": ("maya-cand.jpg", make_reference_image("maya-candidate", (640, 960)), "image/jpeg")},
                   data={"category": "other"}).json()["reference_asset"]
rejected_row = {"ref_id": "ref_maya-rejected", "kind": "character_full", "image_url": "https://val-cdn.local/maya-rejected.jpg",
                "category": "other", "approval_state": "rejected", "source_kind": "uploaded", "source_shot_id": "reference-url",
                "target_type": "character", "target_id": CHARACTER_ID, "project_id": PROJECT_ID}
client.post(f"{LIB}/character/{CHARACTER_ID}", json=rejected_row).raise_for_status()
record("candidate_and_rejected_registered", "OK", f"cand={CAND['ref_id']} rej={rejected_row['ref_id']}")

client.post(f"{LIB}/character/{CHARACTER_ID}/{uploaded_char['ref_id']}/approve").raise_for_status()
for name in url_char_refs:
    client.post(f"{LIB}/character/{CHARACTER_ID}/{url_char_refs[name]['ref_id']}/approve").raise_for_status()
client.post(f"{LIB}/setting/{LOCATION}/{uploaded_setting['ref_id']}/approve").raise_for_status()
client.post(f"{LIB}/setting/{LOCATION}/{url_setting_ref['ref_id']}/approve").raise_for_status()
record("supporting_approved", "OK")

for target, tid in (("character", CHARACTER_ID), ("setting", LOCATION)):
    snap = client.get(f"{LIB}/{target}/{tid}").json()
    record(f"library_{target}", "OK", json.dumps({k: snap[k] for k in ("canonical", "supporting", "candidates", "coverage")}, default=str)[:400])

# ══ 5. Fail-closed probes ════════════════════════════════════════════════
def probe_submit(shot_id: str, prompt: str, refs: list[str] | None = None) -> tuple[int, str, str]:
    params = {"project_id": PROJECT_ID, "shot_id": shot_id, "provider": "local_ltx", "prompt": prompt,
              "parameters": json.dumps(RESOLUTION_PARAMS)}
    if refs is not None:
        params["reference_assets"] = json.dumps(refs)
    response = client.post(f"{BASE}/api/f51/studio/render/jobs", params=params)
    if response.status_code != 200:
        return response.status_code, "", response.text[:220]
    job_id = response.json()["job_id"]
    submit = client.post(f"{BASE}/api/f51/studio/render/jobs/{job_id}/submit")
    detail = ""
    if submit.status_code != 200:
        body = submit.json()
        detail = body.get("detail") if isinstance(body.get("detail"), str) else json.dumps(body.get("detail") or body)
    return submit.status_code, job_id, detail[:260]

# Candidate-only character (Extra has only an unapproved upload)
response = client.post(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/characters", json={"name": "Extra"})
response.raise_for_status()
EXTRA_ID = response.json()["character"]["id"]
client.post(f"{LIB}/character/{EXTRA_ID}/upload",
            files={"file": ("extra-cand.jpg", make_reference_image("maya-candidate", (320, 480)), "image/jpeg")},
            data={"category": "other"}).raise_for_status()
scene_extra = create_scene("Extra Only", "Extra alone in the loft.", ["Extra"])
code, job_id, detail = probe_submit(f"{scene_extra}_shot_001", "Extra alone in the loft, close up.")
ok = code == 409 and "canonical_character_reference_missing" in detail
record("failclosed_candidate_only", "BLOCKED" if ok else "FAIL", f"http={code} {detail[:150]}")
if job_id:
    client.delete(f"{BASE}/api/f51/studio/render/jobs/{job_id}")

# Wrong-character reference (Extra2's scene referencing Maya's wardrobe URL)
response = client.post(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/characters", json={"name": "Extra2"})
response.raise_for_status()
scene_wrong = create_scene("Wrong Probe", "Extra2 alone in the loft.", ["Extra2"])
code, job_id, detail = probe_submit(f"{scene_wrong}_shot_001", "Extra2 stands in the loft.", refs=[f"{URL_BASE}/maya-wardrobe.jpg"])
ok = code == 409
record("failclosed_wrong_character", "BLOCKED" if ok else "FAIL", f"http={code} {detail[:170]}")
if job_id:
    client.delete(f"{BASE}/api/f51/studio/render/jobs/{job_id}")

# Invalid image upload must not register anything
before_rows = client.get(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/reference-assets").json()["count"]
invalid = client.post(f"{LIB}/character/{CHARACTER_ID}/upload",
                      files={"file": ("broken.png", b"not an image at all", "image/png")}, data={"category": "other"})
after_rows = client.get(f"{BASE}/api/f51/studio/projects/{PROJECT_ID}/reference-assets").json()["count"]
ok = invalid.status_code == 400 and before_rows == after_rows
record("failclosed_invalid_image", "BLOCKED" if ok else "FAIL", f"http={invalid.status_code} rows {before_rows}->{after_rows} {str(invalid.json().get('detail'))[:100]}")

# ══ 6. Scene renders (canonical + approved supporting) ═══════════════════
def submit_scene(shot_id: str, prompt: str) -> str:
    params = {"project_id": PROJECT_ID, "shot_id": shot_id, "provider": "local_ltx",
              "prompt": prompt, "reference_assets": json.dumps([face_url]),
              "parameters": json.dumps(RESOLUTION_PARAMS)}
    response = client.post(f"{BASE}/api/f51/studio/render/jobs", params=params)
    assert response.status_code == 200, response.text
    job_id = response.json()["job_id"]
    submit = client.post(f"{BASE}/api/f51/studio/render/jobs/{job_id}/submit")
    assert submit.status_code == 200, submit.text
    record(f"submit_{shot_id}", "OK", f"job={job_id} status={submit.json().get('status')}")
    return job_id

jobs = {
    SHOT_S1: submit_scene(SHOT_S1, "Wide establishing shot: Maya crosses the brick loft interior at dawn, tall industrial windows casting warm light on worn wooden floors. She carries a crumpled letter. Slow dolly forward, anamorphic, natural grade."),
    SHOT_S2: submit_scene(SHOT_S2, "Night interior: Maya stands at the loft window, city glow rim-lighting her face, locs silhouetted against the glass. Dim practical lamps only. Static shot, cinematic contrast."),
}

# Deleted-supporting probe: remove one approved URL ref before the renders resolve.
client.delete(f"{LIB}/character/{CHARACTER_ID}/{url_char_refs['maya-extra']['ref_id']}").raise_for_status()
record("supporting_deleted", "OK", url_char_refs["maya-extra"]["ref_id"])

STATE = {"project_id": PROJECT_ID, "character_id": CHARACTER_ID, "face_url": face_url, "body_url": body_url,
         "jobs": jobs, "scout": scout_job_id, "scout_url": scout_url, "cand": CAND["ref_id"], "rejected": rejected_row["ref_id"],
         "uploaded_char": uploaded_char["ref_id"], "uploaded_setting": uploaded_setting["ref_id"],
         "url_refs": {k: v["ref_id"] for k, v in url_char_refs.items()}, "url_setting": url_setting_ref["ref_id"],
         "env_canonical": "ref_env_confirmed", "env_url": env_url}
Path("/tmp/validation_state.json").write_text(json.dumps(STATE, indent=2))
record("state_written", "OK", "/tmp/validation_state.json")
