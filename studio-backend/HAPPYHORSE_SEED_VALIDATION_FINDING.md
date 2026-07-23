# HappyHorse Seed Validation Finding

## Scope

This is a raw data collection note for `happyhorse-1.1-t2v`.

It expands the prior two-sample check by running 10 same-prompt/same-seed HappyHorse renders, then separately running the adherence scorer 5 times against one static reference image. This file intentionally does not draw a final "does reproduce" or "does not reproduce" conclusion.

## Render Inputs

- Provider: `happyhorse`
- Model: `happyhorse-1.1-t2v`
- Seed: `983559286`
- Resolution: `720P`
- Ratio: `16:9`
- Duration: `5`
- Watermark: `false`
- Raw report: `outputs/renders/happyhorse-seed-validation-10x/happyhorse_seed_validation_10x_raw.json`

Prompt:

```text
People fill the streets. Music, laughter, food stands. Everything is vibrant. Chicago is alive. The L train moves through the skyline. Wide shot. golden hour light. Cinematic, film quality.
```

Expected slots:

| Slot | Expected text |
|---|---|
| `character_state` | `People fill the streets` |
| `action` | `Music, laughter, food stands. Everything is vibrant` |
| `environment_persistence` | `Chicago is alive. The L train moves through the skyline` |
| `camera` | `Wide shot` |
| `lighting` | `golden hour light` |

## 10 Render Repeat Distribution

All 10 runs used the same prompt and the same seed.

| Run | Adherence score | Audio streams after strip |
|---|---:|---:|
| `repeat_01` | `95.70` | `0` |
| `repeat_02` | `94.70` | `0` |
| `repeat_03` | `95.70` | `0` |
| `repeat_04` | `94.70` | `0` |
| `repeat_05` | `94.70` | `0` |
| `repeat_06` | `94.20` | `0` |
| `repeat_07` | `92.70` | `0` |
| `repeat_08` | `94.70` | `0` |
| `repeat_09` | `95.70` | `0` |
| `repeat_10` | `94.20` | `0` |

Distribution:

| Metric | Value |
|---|---:|
| Count | `10` |
| Min | `92.70` |
| Max | `95.70` |
| Mean | `94.70` |
| Sample stdev | `0.9128709291752769` |
| Population stdev | `0.8660254037844386` |

## Scorer-Only Static Image Distribution

Static reference image:

```text
outputs/renders/happyhorse-seed-validation-10x/repeat_01_frame_2.jpg
```

The same static image was passed as all three frame positions for each scorer-only call: `[image, image, image]`. No new render was generated for this scorer-only check.

| Scorer-only run | Adherence score |
|---|---:|
| `scorer_only_01` | `95.70` |
| `scorer_only_02` | `95.70` |
| `scorer_only_03` | `95.70` |
| `scorer_only_04` | `95.70` |
| `scorer_only_05` | `95.70` |

Distribution:

| Metric | Value |
|---|---:|
| Count | `5` |
| Min | `95.70` |
| Max | `95.70` |
| Mean | `95.70` |
| Sample stdev | `0.0` |
| Population stdev | `0.0` |

## Render Artifacts

All listed MP4s are the stripped `*_happyhorse_silent.mp4` outputs returned after the audio-removal step.

| Run | Video path |
|---|---|
| `repeat_01` | `outputs/renders/happyhorse-seed-validation-10x/job-20260717205950-06c4179b-hh_seed_repeat_01_happyhorse_silent.mp4` |
| `repeat_02` | `outputs/renders/happyhorse-seed-validation-10x/job-20260717205950-ce4f965b-hh_seed_repeat_02_happyhorse_silent.mp4` |
| `repeat_03` | `outputs/renders/happyhorse-seed-validation-10x/job-20260717205950-4c868ab7-hh_seed_repeat_03_happyhorse_silent.mp4` |
| `repeat_04` | `outputs/renders/happyhorse-seed-validation-10x/job-20260717210127-62b6600a-hh_seed_repeat_04_happyhorse_silent.mp4` |
| `repeat_05` | `outputs/renders/happyhorse-seed-validation-10x/job-20260717210132-8757d877-hh_seed_repeat_05_happyhorse_silent.mp4` |
| `repeat_06` | `outputs/renders/happyhorse-seed-validation-10x/job-20260717210136-c52f247f-hh_seed_repeat_06_happyhorse_silent.mp4` |
| `repeat_07` | `outputs/renders/happyhorse-seed-validation-10x/job-20260717210313-0228def6-hh_seed_repeat_07_happyhorse_silent.mp4` |
| `repeat_08` | `outputs/renders/happyhorse-seed-validation-10x/job-20260717210314-b3fef9b0-hh_seed_repeat_08_happyhorse_silent.mp4` |
| `repeat_09` | `outputs/renders/happyhorse-seed-validation-10x/job-20260717210314-59854c67-hh_seed_repeat_09_happyhorse_silent.mp4` |
| `repeat_10` | `outputs/renders/happyhorse-seed-validation-10x/job-20260717210456-2e2401d4-hh_seed_repeat_10_happyhorse_silent.mp4` |

## Final Threshold Comparison

The active adherence verdict thresholds are defined in `app/services/adherence_service.py`:

| Verdict path | Threshold logic |
|---|---|
| Pass | `adherence_score >= 80` |
| Correctable retry candidate | `50 <= adherence_score < 80` and `attempt_n < 3` |
| Manual review | `adherence_score < 50`, or correctable score after max attempts |

`app/services/render_retry_service.py` uses `score.verdict` to decide retry behavior. A `pass` returns `should_retry: False`; a `correctable` verdict returns `should_retry: True` only when `attempt_n < MAX_ATTEMPTS`, where `MAX_ATTEMPTS = 3`. It also has a legacy stuck-shot guard, `STUCK_SHOT_THRESHOLD = 5.0`, for score improvement between attempts, but the pass threshold is the relevant cutoff for this same-seed distribution because all observed scores are already above pass.

The HappyHorse 10-render same-prompt/same-seed score range was `92.70` to `95.70`.

The pass threshold, `80`, is safely outside and below that observed range. It is `12.70` points below the lowest observed score, `92.70`.

## Final Conclusion

The observed HappyHorse same-seed score spread is real in the collected data: the 10 runs ranged from `92.70` to `95.70`, with mean `94.70` and sample stdev `0.9128709291752769`. The scorer-only static-image check produced no observed score variance: all 5 scorer-only runs scored `95.70`.

Given the actual retry/pass threshold, the observed seed variance is currently harmless for retry triggering in this test case. The retry system passes any score `>= 80`, and the lowest HappyHorse same-seed score observed here was `92.70`, leaving `12.70` points of margin above the pass cutoff. On these numbers, the spread does not cross, touch, or approach the retry threshold.
