# Release Checklist — before any provider spend, after any restart

## Before any provider spend (paid Runway call)

1. Clean-checkout green: backend suite under `R43K_SOCKET_ONLY=1`, frontend
   `tsc --noEmit` + vitest, and CI green on the branch. Never weaken a test
   to get there.
2. Confirm the board gate: every shot's image prompt is `ready`
   (approved, fresh, within the 1000 UTF-16-unit Runway cap). Canonical text
   is never truncated — over-limit prompts fail closed.
3. Confirm the live backend is the current tree: `GET /health` →
   `git_commit` must equal `git rev-parse HEAD`, and `image_provider` must
   be `runway`. If the commit differs, the process is stale — restart it
   (below), do not spend against it.
4. Back up the database: `studio-backend/scripts/backup_studio_db.sh`
   (timestamped `.backup` + `integrity_check` must print `ok`).

## After any restart

1. Start only via `studio-backend/scripts/start_runway_backend.sh` (unsets
   `DASHSCOPE_*`, pins `DEFAULT_IMAGE_PROVIDER=runway`,
   `RUNWAY_API_ENABLED=true`, `R43K_SOCKET_ONLY=1`, prints the commit).
   To switch the live launchd job (`gui/501/com.aifilmstudio.backend`):
   back up the DB, `launchctl bootout` the job, verify `:8010` is free,
   then `launchctl submit` with the identical command plus the same
   unset/env pins. Never run two listeners on `:8010`.
2. Verify: `GET /health` returns `healthy`, `git_commit` matches the tree
   just started, `process_start_time` is now, `image_provider` is `runway`,
   and the process environment carries no `DASHSCOPE_*` variables.
3. Exercise provider resolution without spending: any legacy alias
   (`qwen-image-max`, `dashscope`, `qwen`, `wanx`) must route to Runway —
   a storyboard call with no approved prompt must fail closed with a
   Runway-attributed error, never a DashScope 404.

## Never

- No force-push, amend, rebase, reset, stash, or clean on release branches.
- No `.env`, `studio.db`, `-wal`/`-shm`, or `.bak` content in any commit.
- No push to a public remote; releases push only to the private remote
  after the authorization gate is approved.
