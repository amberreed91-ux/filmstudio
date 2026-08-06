# Canonical naming and route evidence

## Naming

- `Previs` appears throughout the backend route/service and frontend room/API implementation.
- A whole-word search for `Precise` in non-test application code found only ordinary prose such as “precise correction operations” and “emotionally precise pacing.”
- No `Precise` route, service, model, component, page, table, or API contract exists.
- Canonical surface: **Previs**.
- Canonical review surface: **Screening Room**; `The Theater` is a presentation component/subtitle inside that surface.

## Added/verified route families

### Storyboard

- Project/scene Blueprint create/load.
- Blueprint version list/create/approve/continuity review.
- Shot create/update/delete/reorder/lock/image generation.
- Canonical Storyboard Wall projection.

### Previs

- `POST /api/f51/studio/projects/{project_id}/previs/generate-scene/{scene_id}`
- `GET /api/f51/studio/projects/{project_id}/previs/images/{scene_id}`
- `GET /api/f51/studio/projects/{project_id}/previs/records/{image_id}`
- `POST .../approve`, `.../cancel`, and `.../retry`
- `POST /api/f51/studio/projects/{project_id}/previs/production-packages/{scene_id}`

### Screening Room

- `GET /api/f51/studio/projects/{project_id}/screening/manifest`
- `POST /api/f51/studio/projects/{project_id}/screening/sync`
- `POST /api/f51/studio/projects/{project_id}/screening/outputs/{output_id}/approve`
- `GET /api/f51/studio/projects/{project_id}/screening/media/{output_id}`

### Film Cut / Editorial

- `GET /api/f51/studio/projects/{project_id}/film-cut`
- `GET /api/f51/studio/projects/{project_id}/film-cut/versions`
- `PUT /api/f51/studio/projects/{project_id}/film-cut/timeline`
- `GET /api/f51/studio/projects/{project_id}/film-cut/compare`
- `POST /api/f51/studio/projects/{project_id}/film-cut/{cut_id}/approve`
- Existing Editorial analysis/list/get/apply/application routes remain active.
