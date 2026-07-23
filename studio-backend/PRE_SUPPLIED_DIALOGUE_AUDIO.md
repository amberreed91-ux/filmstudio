# Pre-supplied shot dialogue audio

The scene assembly audio pipeline accepts a local, pre-rendered dialogue file
for each shot. When the file exists, it is used before any CosyVoice, Piper,
ElevenLabs, or Fish Audio call.

## File location and naming

Place each file at:

```text
studio-backend/outputs/audio/<project_id>/<scene_id>/pre_supplied/<shot_id>.<ext>
```

For *I Was Reborn* scene 002:

```text
studio-backend/outputs/audio/project_3dba9330f43a/scene_002/pre_supplied/
  shot_scene_002_001.wav
  shot_scene_002_002.wav
  shot_scene_002_003.wav
  shot_scene_002_004.wav
```

Supported extensions, in lookup order, are `.wav`, `.mp3`, `.m4a`, `.flac`,
`.ogg`, and `.aac`. WAV is preferred. Each file must contain the complete
dialogue for that shot, already timed and ordered as desired. The pipeline
normalizes it to mono, 22,050 Hz, 16-bit PCM WAV before baking it into the shot.
Only leading edge silence is trimmed; internal and trailing pauses are preserved
because SSML timing and multi-line shot performance can depend on them. FFmpeg
must therefore be installed.

Run the existing local scene-002 assembly after dropping in all four files:

```bash
cd studio-backend
.venv/bin/python scripts/render_i_was_reborn_scene_002_assembly.py \
  --dialogue-provider cosyvoice
```

The provider argument remains the requested-provider label, but no provider is
called for a shot that has a matching pre-supplied file.

## Audit behavior

Each shot result and the final assembly report include:

- `dialogue_source`: `pre_supplied`, `live_provider`, `mock`, or `none`
- `dialogue_source_path`: the local input path when `pre_supplied` was used
- `dialogue_provider`: the requested/resolved provider

The service also emits `SHOT_DIALOGUE_SOURCE` logs with the project, scene,
shot, provider, source, and local source path. A present but invalid local file
fails that shot without falling back to a live provider, preventing an
unexpected external call.

## Directed CosyVoice performance pattern

CosyVoice/Qwen dialogue should be directed per line before it is baked into
pre-supplied shot files. Each line may carry:

- `text`: the plain screenplay line, preserved for reports and editorial review.
- `emotional_subtext`: a natural-language acting direction rooted in the beat,
  not a generic emotion tag.
- `pacing_tag`: a compact rhythm note for the actor/TTS model.
- `ssml_text`: optional exact TTS payload when timing or stress changes the
  meaning. Use this sparingly for beats like a pre-line pause, one stressed
  word, or a meaningful hesitation.

Scene 002 is the worked example. Run:

```bash
cd studio-backend
.venv/bin/python scripts/render_i_was_reborn_scene_002_assembly.py \
  --dry-run-directed-report
```

The dry run makes no provider calls. It writes the planned per-line payloads to:

```text
studio-backend/outputs/real_render_validation/scene_002_directed_dialogue_preflight.json
```

Use that report to confirm voice-specific instruction compatibility before
spending live TTS calls. For the current scene-002 cast, DRE/`longanyang` should
show `instruction_mode: cosyvoice_fixed`, while MAYA/`longwanjun_v3` should show
`instruction_mode: none` with the richer acting note preserved in
`performance_direction`.

Then run the live regeneration:

```bash
cd studio-backend
.venv/bin/python scripts/render_i_was_reborn_scene_002_assembly.py \
  --dialogue-provider cosyvoice \
  --regenerate-pre-supplied
```

That script enriches the four persisted shot dialogue groups with specific
directions such as:

- DRE, `I need you to understand something.`: tense and controlled, trying to
  justify himself before he has said the unforgivable part.
- MAYA, `That's funny.`: bitter and flat, not actually amused.
- DRE, `There's not enough...`: strained rationalizing, almost pleading
  underneath the threat.
- MAYA, `I remember dying. So why am I here?`: quiet and disoriented, not
  performative.

Only high-impact timing lines use SSML in the example:

- `What?` starts after a short beat.
- `So you decided that for all of us.` lets the pressure fall after `you`.
- `Someone had to.` starts after a longer pause.

The live generation report is written to:

```text
studio-backend/outputs/real_render_validation/scene_002_directed_dialogue_report.json
```

Scene 002's current four-shot artifact is an audio proof only. It is not
lip-synced and does not satisfy the stored previs/Co-Director shot structure.
Check the manifest before using it downstream:

```text
studio-backend/outputs/real_render_validation/listen_review/scene_002_directed_dialogue_manifest.json
```

For future scenes, prefer this order:

1. Pull explicit line-level beat data from Co-Director or scene intelligence
   if present.
2. If no line-level data exists, define the beats in the scene render/probe
   harness as scene-specific data, not global heuristics.
3. Pass `emotional_subtext` and `pacing_tag` through the existing
`dialogue_lines` dictionaries.
4. Respect each CosyVoice stock voice's Instruct support. `longanyang` accepts
   DashScope's fixed Chinese `instruction` format (`你说话的情感是<emotion>。`).
   `longwanjun_v3` does not support `instruction`; keep Maya's rich note in
   `performance_direction`/sources and use SSML where timing matters.
5. Add `ssml_text` only where timing carries meaning. For CosyVoice v3 stock
   voices, prefer `<break>` over `<emphasis>`; live scene-002 testing showed
   `<emphasis>` can be rejected as an invalid SSML label even when the voice
   supports SSML generally.
6. Save the generation report beside the rendered artifact so reviewers can
   audit the exact instruction and SSML payload used for every line.
