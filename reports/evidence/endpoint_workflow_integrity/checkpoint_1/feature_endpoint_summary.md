# Feature Endpoint Summary

## Storyboard / Storyboard Blueprint
Count: 14

- `POST /api/f51/studio/projects/{project_id}/scenes/{scene_id}/storyboard` :: `generate_scene_storyboard_api_f51_studio_projects__project_id__scenes__scene_id__storyboard_post`
- `GET /api/f51/studio/projects/{project_id}/scenes/{scene_id}/storyboard-blueprint` :: `get_storyboard_blueprint_api_f51_studio_projects__project_id__scenes__scene_id__storyboard_blueprint_get`
- `POST /api/f51/studio/projects/{project_id}/scenes/{scene_id}/storyboard-blueprint` :: `create_storyboard_blueprint_api_f51_studio_projects__project_id__scenes__scene_id__storyboard_blueprint_post`
- `GET /api/f51/studio/projects/{project_id}/storyboard-blueprints` :: `list_storyboard_blueprints_api_f51_studio_projects__project_id__storyboard_blueprints_get`
- `POST /api/f51/studio/projects/{project_id}/storyboard-blueprints/backfill` :: `backfill_storyboard_blueprints_api_f51_studio_projects__project_id__storyboard_blueprints_backfill_post`
- `GET /api/f51/studio/projects/{project_id}/storyboard-wall` :: `get_storyboard_wall_api_f51_studio_projects__project_id__storyboard_wall_get`
- `POST /api/f51/studio/projects/{project_id}/storyboard-wall/update-shot` :: `update_storyboard_shot_api_f51_studio_projects__project_id__storyboard_wall_update_shot_post`
- `PATCH /api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}` :: `update_storyboard_shot_api_f51_studio_storyboard_blueprints__blueprint_id__shots__storyboard_shot_id__patch`
- `POST /api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/image` :: `generate_storyboard_shot_image_api_f51_studio_storyboard_blueprints__blueprint_id__shots__storyboard_shot_id__image_post`
- `PATCH /api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/lock` :: `lock_storyboard_shot_api_f51_studio_storyboard_blueprints__blueprint_id__shots__storyboard_shot_id__lock_patch`
- `POST /api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render` :: `render_storyboard_shot_api_f51_studio_storyboard_blueprints__blueprint_id__shots__storyboard_shot_id__render_post`
- `POST /api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render-contract` :: `build_storyboard_render_contract_api_f51_studio_storyboard_blueprints__blueprint_id__shots__storyboard_shot_id__render_contract_post`
- `POST /api/f51/studio/storyboard-blueprints/{blueprint_id}/versions/{version_id}/approve` :: `approve_storyboard_version_api_f51_studio_storyboard_blueprints__blueprint_id__versions__version_id__approve_post`
- `POST /api/f51/studio/storyboard-blueprints/{blueprint_id}/versions/{version_id}/continuity-review` :: `run_storyboard_continuity_review_api_f51_studio_storyboard_blueprints__blueprint_id__versions__version_id__continuity_review_post`

## Previs / Rough Previs
Count: 8

- `POST /api/f51/studio/projects/{project_id}/previs/director-notes` :: `previs_director_notes_api_f51_studio_projects__project_id__previs_director_notes_post`
- `POST /api/f51/studio/projects/{project_id}/previs/enhance-prompt` :: `enhance_prompt_api_f51_studio_projects__project_id__previs_enhance_prompt_post`
- `POST /api/f51/studio/projects/{project_id}/previs/generate-all` :: `generate_all_previs_api_f51_studio_projects__project_id__previs_generate_all_post`
- `POST /api/f51/studio/projects/{project_id}/previs/generate-scene/{scene_id}` :: `generate_scene_previs_api_f51_studio_projects__project_id__previs_generate_scene__scene_id__post`
- `POST /api/f51/studio/projects/{project_id}/previs/generation-settings` :: `recommend_generation_settings_api_f51_studio_projects__project_id__previs_generation_settings_post`
- `GET /api/f51/studio/projects/{project_id}/previs/images/{scene_id}` :: `get_scene_previs_images_api_f51_studio_projects__project_id__previs_images__scene_id__get`
- `POST /api/f51/studio/projects/{project_id}/previs/shot-count` :: `recommend_shot_count_api_f51_studio_projects__project_id__previs_shot_count_post`
- `PATCH /api/f51/studio/projects/{project_id}/scenes/{scene_id}/previs/seed` :: `toggle_previs_seed_lock_api_f51_studio_projects__project_id__scenes__scene_id__previs_seed_patch`

## Precise
Count: 0


## Theatre / Theater
Count: 0


## Screening Room
Count: 11

- `POST /api/f51/studio/memory/{project_id}/review` :: `update_review_memory_api_f51_studio_memory__project_id__review_post`
- `PUT /api/f51/studio/projects/{project_id}/collaboration/screening` :: `set_collaboration_screening_api_f51_studio_projects__project_id__collaboration_screening_put`
- `POST /api/f51/studio/projects/{project_id}/review-shot` :: `review_shot_api_f51_studio_projects__project_id__review_shot_post`
- `PUT /api/f51/studio/projects/{project_id}/scene-review` :: `update_scene_review_api_f51_studio_projects__project_id__scene_review_put`
- `POST /api/f51/studio/projects/{project_id}/short-film-review` :: `create_short_film_review_api_f51_studio_projects__project_id__short_film_review_post`
- `GET /api/f51/studio/projects/{project_id}/short-film-review/latest` :: `get_latest_short_film_review_api_f51_studio_projects__project_id__short_film_review_latest_get`
- `POST /api/f51/studio/projects/{project_id}/short-film-review/{review_id}/decision` :: `update_short_film_review_decision_api_f51_studio_projects__project_id__short_film_review__review_id__decision_post`
- `GET /api/f51/studio/projects/{project_id}/short-film-reviews` :: `list_short_film_reviews_api_f51_studio_projects__project_id__short_film_reviews_get`
- `POST /api/f51/studio/projects/{project_id}/simulate-screening` :: `simulate_screening_api_f51_studio_projects__project_id__simulate_screening_post`
- `POST /api/f51/studio/storyboard-blueprints/{blueprint_id}/versions/{version_id}/continuity-review` :: `run_storyboard_continuity_review_api_f51_studio_storyboard_blueprints__blueprint_id__versions__version_id__continuity_review_post`
- `GET /api/projects/{project_id}/performance-intelligence/scenes/{scene_id}/screening-context` :: `get_performance_screening_context_api_projects__project_id__performance_intelligence_scenes__scene_id__screening_context_get`

## Production Board / Scene Production
Count: 41

- `GET /api/f51/studio/production-acceptance/{acceptance_id}` :: `get_production_acceptance_report_api_f51_studio_production_acceptance__acceptance_id__get`
- `GET /api/f51/studio/production-queue/diagnostics` :: `get_queue_diagnostics_api_f51_studio_production_queue_diagnostics_get`
- `POST /api/f51/studio/production-queue/items` :: `create_queue_item_api_f51_studio_production_queue_items_post`
- `GET /api/f51/studio/production-queue/items/{queue_item_id}` :: `get_queue_item_api_f51_studio_production_queue_items__queue_item_id__get`
- `POST /api/f51/studio/production-queue/items/{queue_item_id}/cancel` :: `cancel_queue_item_api_f51_studio_production_queue_items__queue_item_id__cancel_post`
- `GET /api/f51/studio/production-queue/items/{queue_item_id}/events` :: `list_queue_events_api_f51_studio_production_queue_items__queue_item_id__events_get`
- `POST /api/f51/studio/production-queue/items/{queue_item_id}/retry` :: `retry_queue_item_api_f51_studio_production_queue_items__queue_item_id__retry_post`
- `GET /api/f51/studio/production-queue/projects/{project_id}/items` :: `list_project_queue_items_api_f51_studio_production_queue_projects__project_id__items_get`
- `POST /api/f51/studio/production-queue/projects/{project_id}/scenes/{scene_id}/queue` :: `queue_scene_generation_api_f51_studio_production_queue_projects__project_id__scenes__scene_id__queue_post`
- `GET /api/f51/studio/production-queue/projects/{project_id}/summary` :: `get_project_queue_summary_api_f51_studio_production_queue_projects__project_id__summary_get`
- `POST /api/f51/studio/production-queue/recover` :: `recover_queue_leases_api_f51_studio_production_queue_recover_post`
- `GET /api/f51/studio/production-queue/summary` :: `get_global_queue_summary_api_f51_studio_production_queue_summary_get`
- `POST /api/f51/studio/production-queue/worker/run-once` :: `run_queue_worker_once_api_f51_studio_production_queue_worker_run_once_post`
- `POST /api/f51/studio/projects/{project_id}/generate-scenes` :: `generate_scenes_api_f51_studio_projects__project_id__generate_scenes_post`
- `POST /api/f51/studio/projects/{project_id}/previs/generate-scene/{scene_id}` :: `generate_scene_previs_api_f51_studio_projects__project_id__previs_generate_scene__scene_id__post`
- `GET /api/f51/studio/projects/{project_id}/production-acceptance` :: `list_production_acceptance_reports_api_f51_studio_projects__project_id__production_acceptance_get`
- `POST /api/f51/studio/projects/{project_id}/production-acceptance` :: `run_production_acceptance_api_f51_studio_projects__project_id__production_acceptance_post`
- `GET /api/f51/studio/projects/{project_id}/production-acceptance/latest` :: `latest_production_acceptance_api_f51_studio_projects__project_id__production_acceptance_latest_get`
- `GET /api/f51/studio/projects/{project_id}/production-design/assessments` :: `list_production_design_assessments_api_f51_studio_projects__project_id__production_design_assessments_get`
- `POST /api/f51/studio/projects/{project_id}/production-design/assessments` :: `create_production_design_assessment_api_f51_studio_projects__project_id__production_design_assessments_post`
- `GET /api/f51/studio/projects/{project_id}/production-design/costume-records` :: `list_production_design_costume_records_api_f51_studio_projects__project_id__production_design_costume_records_get`
- `POST /api/f51/studio/projects/{project_id}/production-design/costume-records` :: `create_production_design_costume_record_api_f51_studio_projects__project_id__production_design_costume_records_post`
- `POST /api/f51/studio/projects/{project_id}/production-design/decisions` :: `save_production_design_decision_api_f51_studio_projects__project_id__production_design_decisions_post`
- `PATCH /api/f51/studio/projects/{project_id}/production-design/decisions/{decision_id}` :: `update_production_design_decision_api_f51_studio_projects__project_id__production_design_decisions__decision_id__patch`
- `GET /api/f51/studio/projects/{project_id}/production-design/department-signal` :: `get_production_design_department_signal_api_f51_studio_projects__project_id__production_design_department_signal_get`
- `GET /api/f51/studio/projects/{project_id}/production-design/environment-profiles` :: `list_production_design_environment_profiles_api_f51_studio_projects__project_id__production_design_environment_profiles_get`
- `POST /api/f51/studio/projects/{project_id}/production-design/environment-profiles` :: `create_production_design_environment_profile_api_f51_studio_projects__project_id__production_design_environment_profiles_post`
- `GET /api/f51/studio/projects/{project_id}/production-design/observations` :: `list_production_design_observations_api_f51_studio_projects__project_id__production_design_observations_get`
- `POST /api/f51/studio/projects/{project_id}/production-design/observations` :: `create_production_design_observation_api_f51_studio_projects__project_id__production_design_observations_post`
- `GET /api/f51/studio/projects/{project_id}/production-design/plans` :: `list_production_design_plans_api_f51_studio_projects__project_id__production_design_plans_get`
- `POST /api/f51/studio/projects/{project_id}/production-design/plans` :: `create_production_design_plan_api_f51_studio_projects__project_id__production_design_plans_post`
- `GET /api/f51/studio/projects/{project_id}/production-design/plans/{plan_id}` :: `get_production_design_plan_api_f51_studio_projects__project_id__production_design_plans__plan_id__get`
- `GET /api/f51/studio/projects/{project_id}/production-design/prop-records` :: `list_production_design_prop_records_api_f51_studio_projects__project_id__production_design_prop_records_get`
- `POST /api/f51/studio/projects/{project_id}/production-design/prop-records` :: `create_production_design_prop_record_api_f51_studio_projects__project_id__production_design_prop_records_post`
- `POST /api/f51/studio/projects/{project_id}/production-design/render-context` :: `build_production_design_render_context_api_f51_studio_projects__project_id__production_design_render_context_post`
- `POST /api/f51/studio/projects/{project_id}/scan` :: `run_production_scan_api_f51_studio_projects__project_id__scan_post`
- `GET /api/f51/studio/projects/{project_id}/scan/{scan_id}` :: `get_production_scan_report_api_f51_studio_projects__project_id__scan__scan_id__get`
- `GET /api/production-recovery/health` :: `health_check_api_production_recovery_health_get`
- `POST /api/production-recovery/recover` :: `start_production_recovery_api_production_recovery_recover_post`
- `POST /api/production-recovery/reset` :: `reset_recovery_state_api_production_recovery_reset_post`
- `GET /api/production-recovery/status` :: `get_recovery_status_api_production_recovery_status_get`

## Rendering
Count: 35

- `POST /api/f51/studio/agents/projects/{project_id}/workflow/render` :: `create_render_request_api_f51_studio_agents_projects__project_id__workflow_render_post`
- `POST /api/f51/studio/clip-revisions/{revision_id}/submit` :: `submit_clip_revision_render_api_f51_studio_clip_revisions__revision_id__submit_post`
- `POST /api/f51/studio/projects/{project_id}/production-design/render-context` :: `build_production_design_render_context_api_f51_studio_projects__project_id__production_design_render_context_post`
- `GET /api/f51/studio/projects/{project_id}/render-batch/{batch_id}` :: `get_render_batch_status_api_f51_studio_projects__project_id__render_batch__batch_id__get`
- `POST /api/f51/studio/projects/{project_id}/render-jobs/{job_id}/retry` :: `retry_render_job_with_context_api_f51_studio_projects__project_id__render_jobs__job_id__retry_post`
- `POST /api/f51/studio/projects/{project_id}/render-mode` :: `set_render_mode_api_f51_studio_projects__project_id__render_mode_post`
- `POST /api/f51/studio/projects/{project_id}/retry-render/{render_id}` :: `retry_render_api_f51_studio_projects__project_id__retry_render__render_id__post`
- `POST /api/f51/studio/projects/{project_id}/scenes/{scene_id}/render-batch` :: `create_render_batch_api_f51_studio_projects__project_id__scenes__scene_id__render_batch_post`
- `POST /api/f51/studio/render/backfill-project-state` :: `backfill_project_state_render_jobs_api_f51_studio_render_backfill_project_state_post`
- `GET /api/f51/studio/render/diagnostics` :: `get_render_diagnostics_api_f51_studio_render_diagnostics_get`
- `GET /api/f51/studio/render/jobs` :: `list_render_jobs_api_f51_studio_render_jobs_get`
- `POST /api/f51/studio/render/jobs` :: `create_render_job_api_f51_studio_render_jobs_post`
- `DELETE /api/f51/studio/render/jobs/{job_id}` :: `delete_render_job_api_f51_studio_render_jobs__job_id__delete`
- `GET /api/f51/studio/render/jobs/{job_id}` :: `get_render_job_api_f51_studio_render_jobs__job_id__get`
- `POST /api/f51/studio/render/jobs/{job_id}/adherence-retry` :: `retry_render_job_for_adherence_api_f51_studio_render_jobs__job_id__adherence_retry_post`
- `POST /api/f51/studio/render/jobs/{job_id}/cancel` :: `cancel_render_job_api_f51_studio_render_jobs__job_id__cancel_post`
- `GET /api/f51/studio/render/jobs/{job_id}/outputs` :: `get_render_job_outputs_api_f51_studio_render_jobs__job_id__outputs_get`
- `POST /api/f51/studio/render/jobs/{job_id}/queue` :: `queue_existing_render_job_api_f51_studio_render_jobs__job_id__queue_post`
- `POST /api/f51/studio/render/jobs/{job_id}/reconcile` :: `reconcile_render_job_api_f51_studio_render_jobs__job_id__reconcile_post`
- `POST /api/f51/studio/render/jobs/{job_id}/refresh-url` :: `refresh_render_job_output_url_api_f51_studio_render_jobs__job_id__refresh_url_post`
- `POST /api/f51/studio/render/jobs/{job_id}/retry` :: `retry_render_job_api_f51_studio_render_jobs__job_id__retry_post`
- `GET /api/f51/studio/render/jobs/{job_id}/status` :: `get_render_job_status_api_f51_studio_render_jobs__job_id__status_get`
- `POST /api/f51/studio/render/jobs/{job_id}/submit` :: `submit_render_job_api_f51_studio_render_jobs__job_id__submit_post`
- `PATCH /api/f51/studio/render/projects/{project_id}/scenes/{scene_id}/shots/{shot_id}/seed` :: `update_shot_seed_api_f51_studio_render_projects__project_id__scenes__scene_id__shots__shot_id__seed_patch`
- `GET /api/f51/studio/render/projects/{project_id}/shots/{shot_id}/recommended-duration` :: `get_recommended_shot_duration_api_f51_studio_render_projects__project_id__shots__shot_id__recommended_duration_get`
- `GET /api/f51/studio/render/providers` :: `list_providers_api_f51_studio_render_providers_get`
- `POST /api/f51/studio/render/providers` :: `configure_provider_api_f51_studio_render_providers_post`
- `GET /api/f51/studio/render/providers/{provider_id}` :: `get_provider_api_f51_studio_render_providers__provider_id__get`
- `POST /api/f51/studio/render/providers/{provider_id}/disable` :: `disable_provider_api_f51_studio_render_providers__provider_id__disable_post`
- `POST /api/f51/studio/render/providers/{provider_id}/enable` :: `enable_provider_api_f51_studio_render_providers__provider_id__enable_post`
- `POST /api/f51/studio/render/recover-output-urls` :: `recover_render_output_urls_api_f51_studio_render_recover_output_urls_post`
- `POST /api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render` :: `render_storyboard_shot_api_f51_studio_storyboard_blueprints__blueprint_id__shots__storyboard_shot_id__render_post`
- `POST /api/f51/studio/storyboard-blueprints/{blueprint_id}/shots/{storyboard_shot_id}/render-contract` :: `build_storyboard_render_contract_api_f51_studio_storyboard_blueprints__blueprint_id__shots__storyboard_shot_id__render_contract_post`
- `POST /api/projects/{project_id}/cinematography/render-context` :: `build_camera_grammar_render_context_api_projects__project_id__cinematography_render_context_post`
- `POST /api/projects/{project_id}/colorist/render-context` :: `build_color_render_context_api_projects__project_id__colorist_render_context_post`

## Revisions
Count: 13

- `GET /api/f51/studio/clip-revisions/{revision_id}` :: `get_clip_revision_api_f51_studio_clip_revisions__revision_id__get`
- `POST /api/f51/studio/clip-revisions/{revision_id}/cancel` :: `cancel_clip_revision_api_f51_studio_clip_revisions__revision_id__cancel_post`
- `POST /api/f51/studio/clip-revisions/{revision_id}/complete-from-job` :: `complete_clip_revision_from_job_api_f51_studio_clip_revisions__revision_id__complete_from_job_post`
- `POST /api/f51/studio/clip-revisions/{revision_id}/submit` :: `submit_clip_revision_render_api_f51_studio_clip_revisions__revision_id__submit_post`
- `POST /api/f51/studio/production-queue/items/{queue_item_id}/retry` :: `retry_queue_item_api_f51_studio_production_queue_items__queue_item_id__retry_post`
- `GET /api/f51/studio/projects/{project_id}/clip-revisions` :: `list_clip_revisions_for_project_api_f51_studio_projects__project_id__clip_revisions_get`
- `POST /api/f51/studio/projects/{project_id}/clip-revisions` :: `create_clip_revision_api_f51_studio_projects__project_id__clip_revisions_post`
- `GET /api/f51/studio/projects/{project_id}/editorial-revision-intelligence` :: `get_editorial_revision_intelligence_api_f51_studio_projects__project_id__editorial_revision_intelligence_get`
- `POST /api/f51/studio/projects/{project_id}/render-jobs/{job_id}/retry` :: `retry_render_job_with_context_api_f51_studio_projects__project_id__render_jobs__job_id__retry_post`
- `POST /api/f51/studio/projects/{project_id}/restitch-with-revisions` :: `restitch_project_with_revisions_api_f51_studio_projects__project_id__restitch_with_revisions_post`
- `POST /api/f51/studio/projects/{project_id}/retry-render/{render_id}` :: `retry_render_api_f51_studio_projects__project_id__retry_render__render_id__post`
- `POST /api/f51/studio/render/jobs/{job_id}/adherence-retry` :: `retry_render_job_for_adherence_api_f51_studio_render_jobs__job_id__adherence_retry_post`
- `POST /api/f51/studio/render/jobs/{job_id}/retry` :: `retry_render_job_api_f51_studio_render_jobs__job_id__retry_post`

## Editorial
Count: 7

- `GET /api/f51/studio/projects/{project_id}/editorial-intelligence` :: `list_editorial_intelligence_api_f51_studio_projects__project_id__editorial_intelligence_get`
- `POST /api/f51/studio/projects/{project_id}/editorial-intelligence/analyze` :: `analyze_editorial_intelligence_api_f51_studio_projects__project_id__editorial_intelligence_analyze_post`
- `GET /api/f51/studio/projects/{project_id}/editorial-intelligence/applications` :: `list_editorial_applications_api_f51_studio_projects__project_id__editorial_intelligence_applications_get`
- `GET /api/f51/studio/projects/{project_id}/editorial-intelligence/latest` :: `get_latest_editorial_intelligence_api_f51_studio_projects__project_id__editorial_intelligence_latest_get`
- `GET /api/f51/studio/projects/{project_id}/editorial-intelligence/{analysis_id}` :: `get_editorial_intelligence_api_f51_studio_projects__project_id__editorial_intelligence__analysis_id__get`
- `POST /api/f51/studio/projects/{project_id}/editorial-intelligence/{analysis_id}/apply` :: `apply_editorial_decisions_api_f51_studio_projects__project_id__editorial_intelligence__analysis_id__apply_post`
- `GET /api/f51/studio/projects/{project_id}/editorial-revision-intelligence` :: `get_editorial_revision_intelligence_api_f51_studio_projects__project_id__editorial_revision_intelligence_get`

## Film Cut / Timeline
Count: 4

- `POST /api/f51/studio/projects/{project_id}/assemble-film` :: `assemble_film_endpoint_api_f51_studio_projects__project_id__assemble_film_post`
- `GET /api/f51/studio/projects/{project_id}/assembly-status` :: `get_assembly_status_api_f51_studio_projects__project_id__assembly_status_get`
- `PUT /api/f51/studio/projects/{project_id}/film-cut` :: `update_film_cut_api_f51_studio_projects__project_id__film_cut_put`
- `GET /api/f51/studio/projects/{project_id}/timeline-intelligence` :: `get_project_timeline_intelligence_api_f51_studio_projects__project_id__timeline_intelligence_get`

## Project State
Count: 415

- `GET /api/f51/studio/agents/projects/{project_id}/activities` :: `get_activities_api_f51_studio_agents_projects__project_id__activities_get`
- `GET /api/f51/studio/agents/projects/{project_id}/ownership` :: `get_project_ownership_api_f51_studio_agents_projects__project_id__ownership_get`
- `POST /api/f51/studio/agents/projects/{project_id}/ownership` :: `create_project_ownership_api_f51_studio_agents_projects__project_id__ownership_post`
- `GET /api/f51/studio/agents/projects/{project_id}/tasks` :: `get_project_tasks_api_f51_studio_agents_projects__project_id__tasks_get`
- `POST /api/f51/studio/agents/projects/{project_id}/tasks` :: `create_task_api_f51_studio_agents_projects__project_id__tasks_post`
- `POST /api/f51/studio/agents/projects/{project_id}/workflow/render` :: `create_render_request_api_f51_studio_agents_projects__project_id__workflow_render_post`
- `POST /api/f51/studio/agents/projects/{project_id}/workflow/script-analysis` :: `run_script_analysis_api_f51_studio_agents_projects__project_id__workflow_script_analysis_post`
- `POST /api/f51/studio/audience-simulator/projects/{project_id}/scenes/{scene_id}/simulate` :: `simulate_scene_audience_api_f51_studio_audience_simulator_projects__project_id__scenes__scene_id__simulate_post`
- `POST /api/f51/studio/audience-simulator/projects/{project_id}/simulate` :: `simulate_project_audience_api_f51_studio_audience_simulator_projects__project_id__simulate_post`
- `GET /api/f51/studio/crew/guardrails/project/{project_id}` :: `get_project_guardrails_status_api_f51_studio_crew_guardrails_project__project_id__get`
- `POST /api/f51/studio/crew/guardrails/project/{project_id}/emergency-stop` :: `emergency_stop_project_api_f51_studio_crew_guardrails_project__project_id__emergency_stop_post`
- `POST /api/f51/studio/crew/guardrails/project/{project_id}/reset` :: `reset_project_guardrails_api_f51_studio_crew_guardrails_project__project_id__reset_post`
- `GET /api/f51/studio/crew/projects/{project_id}` :: `get_project_api_f51_studio_crew_projects__project_id__get`
- `POST /api/f51/studio/crew/projects/{project_id}/adaptation/approval` :: `record_approval_api_f51_studio_crew_projects__project_id__adaptation_approval_post`
- `GET /api/f51/studio/crew/projects/{project_id}/adaptation/compare/{scene_id}` :: `compare_iterations_api_f51_studio_crew_projects__project_id__adaptation_compare__scene_id__get`
- `POST /api/f51/studio/crew/projects/{project_id}/adaptation/consistency-check` :: `check_consistency_api_f51_studio_crew_projects__project_id__adaptation_consistency_check_post`
- `GET /api/f51/studio/crew/projects/{project_id}/adaptation/decisions` :: `get_adaptation_decisions_api_f51_studio_crew_projects__project_id__adaptation_decisions_get`
- `GET /api/f51/studio/crew/projects/{project_id}/adaptation/evolution` :: `get_evolution_metrics_api_f51_studio_crew_projects__project_id__adaptation_evolution_get`
- `POST /api/f51/studio/crew/projects/{project_id}/adaptation/feedback` :: `record_feedback_api_f51_studio_crew_projects__project_id__adaptation_feedback_post`
- `POST /api/f51/studio/crew/projects/{project_id}/adaptation/iteration` :: `record_iteration_api_f51_studio_crew_projects__project_id__adaptation_iteration_post`
- `GET /api/f51/studio/crew/projects/{project_id}/adaptation/iteration/{scene_id}/{iteration_number}` :: `get_iteration_api_f51_studio_crew_projects__project_id__adaptation_iteration__scene_id___iteration_number__get`
- `GET /api/f51/studio/crew/projects/{project_id}/adaptation/metrics` :: `get_evolution_metrics_api_f51_studio_crew_projects__project_id__adaptation_metrics_get`
- `GET /api/f51/studio/crew/projects/{project_id}/adaptation/patterns` :: `get_established_patterns_api_f51_studio_crew_projects__project_id__adaptation_patterns_get`
- `GET /api/f51/studio/crew/projects/{project_id}/adaptation/project-evolution` :: `get_project_evolution_api_f51_studio_crew_projects__project_id__adaptation_project_evolution_get`
- `GET /api/f51/studio/crew/projects/{project_id}/adaptation/scene-evolution/{scene_id}` :: `get_scene_evolution_api_f51_studio_crew_projects__project_id__adaptation_scene_evolution__scene_id__get`
- `POST /api/f51/studio/crew/projects/{project_id}/adaptation/style-boundaries` :: `set_style_boundaries_api_f51_studio_crew_projects__project_id__adaptation_style_boundaries_post`
- `GET /api/f51/studio/crew/projects/{project_id}/adaptation/suggestions` :: `get_pattern_suggestions_api_f51_studio_crew_projects__project_id__adaptation_suggestions_get`
- `GET /api/f51/studio/crew/projects/{project_id}/adaptation/trajectory/{scene_id}` :: `get_improvement_trajectory_api_f51_studio_crew_projects__project_id__adaptation_trajectory__scene_id__get`
- `POST /api/f51/studio/crew/projects/{project_id}/adaptation/user-override` :: `set_user_override_api_f51_studio_crew_projects__project_id__adaptation_user_override_post`
- `POST /api/f51/studio/crew/projects/{project_id}/agent-loop/start` :: `start_agent_loop_api_f51_studio_crew_projects__project_id__agent_loop_start_post`
- `GET /api/f51/studio/crew/projects/{project_id}/agent-loop/status` :: `get_agent_loop_status_endpoint_api_f51_studio_crew_projects__project_id__agent_loop_status_get`
- `POST /api/f51/studio/crew/projects/{project_id}/agent-loop/stop` :: `stop_agent_loop_api_f51_studio_crew_projects__project_id__agent_loop_stop_post`
- `POST /api/f51/studio/crew/projects/{project_id}/agent-loop/trigger` :: `trigger_agent_execution_api_f51_studio_crew_projects__project_id__agent_loop_trigger_post`
- `POST /api/f51/studio/crew/projects/{project_id}/deviation/apply` :: `apply_deviation_api_f51_studio_crew_projects__project_id__deviation_apply_post`
- `POST /api/f51/studio/crew/projects/{project_id}/deviation/check` :: `check_deviation_opportunity_api_f51_studio_crew_projects__project_id__deviation_check_post`
- `POST /api/f51/studio/crew/projects/{project_id}/deviation/custom-inversions` :: `set_custom_inversions_api_f51_studio_crew_projects__project_id__deviation_custom_inversions_post`
- `GET /api/f51/studio/crew/projects/{project_id}/deviation/history` :: `get_deviation_history_api_f51_studio_crew_projects__project_id__deviation_history_get`
- `GET /api/f51/studio/crew/projects/{project_id}/deviation/stats` :: `get_deviation_stats_api_f51_studio_crew_projects__project_id__deviation_stats_get`
- `POST /api/f51/studio/crew/projects/{project_id}/deviation/thresholds` :: `set_deviation_thresholds_api_f51_studio_crew_projects__project_id__deviation_thresholds_post`
- `GET /api/f51/studio/crew/projects/{project_id}/hierarchy/debug` :: `get_hierarchy_debug_api_f51_studio_crew_projects__project_id__hierarchy_debug_get`
- `GET /api/f51/studio/crew/projects/{project_id}/hierarchy/decisions` :: `get_hierarchy_decisions_api_f51_studio_crew_projects__project_id__hierarchy_decisions_get`
- `POST /api/f51/studio/crew/projects/{project_id}/hierarchy/override` :: `set_user_override_api_f51_studio_crew_projects__project_id__hierarchy_override_post`
- `DELETE /api/f51/studio/crew/projects/{project_id}/hierarchy/override/{decision_type}` :: `clear_user_override_api_f51_studio_crew_projects__project_id__hierarchy_override__decision_type__delete`
- `POST /api/f51/studio/crew/projects/{project_id}/hierarchy/resolve` :: `resolve_decision_conflict_api_f51_studio_crew_projects__project_id__hierarchy_resolve_post`
- `POST /api/f51/studio/crew/projects/{project_id}/hierarchy/scene-intent` :: `set_scene_intent_api_f51_studio_crew_projects__project_id__hierarchy_scene_intent_post`
- `GET /api/f51/studio/crew/projects/{project_id}/hierarchy/status` :: `get_hierarchy_status_api_f51_studio_crew_projects__project_id__hierarchy_status_get`
- `POST /api/f51/studio/crew/projects/{project_id}/init` :: `init_project_api_f51_studio_crew_projects__project_id__init_post`
- `GET /api/f51/studio/crew/projects/{project_id}/intelligence` :: `get_crew_intelligence_overview_api_f51_studio_crew_projects__project_id__intelligence_get`
- `GET /api/f51/studio/crew/projects/{project_id}/intelligence/attention` :: `get_crew_creator_attention_api_f51_studio_crew_projects__project_id__intelligence_attention_get`
- `GET /api/f51/studio/crew/projects/{project_id}/intelligence/deliberations` :: `list_crew_deliberations_api_f51_studio_crew_projects__project_id__intelligence_deliberations_get`
- `POST /api/f51/studio/crew/projects/{project_id}/intelligence/deliberations` :: `create_crew_deliberation_api_f51_studio_crew_projects__project_id__intelligence_deliberations_post`
- `GET /api/f51/studio/crew/projects/{project_id}/intelligence/deliberations/{deliberation_id}` :: `get_crew_deliberation_api_f51_studio_crew_projects__project_id__intelligence_deliberations__deliberation_id__get`
- `PATCH /api/f51/studio/crew/projects/{project_id}/intelligence/deliberations/{deliberation_id}` :: `resolve_crew_deliberation_api_f51_studio_crew_projects__project_id__intelligence_deliberations__deliberation_id__patch`
- `GET /api/f51/studio/crew/projects/{project_id}/intelligence/departments` :: `get_crew_department_profiles_api_f51_studio_crew_projects__project_id__intelligence_departments_get`
- `GET /api/f51/studio/crew/projects/{project_id}/intelligence/handoffs` :: `list_crew_handoffs_api_f51_studio_crew_projects__project_id__intelligence_handoffs_get`
- `POST /api/f51/studio/crew/projects/{project_id}/intelligence/handoffs` :: `create_crew_handoff_api_f51_studio_crew_projects__project_id__intelligence_handoffs_post`
- `PATCH /api/f51/studio/crew/projects/{project_id}/intelligence/handoffs/{handoff_id}` :: `update_crew_handoff_api_f51_studio_crew_projects__project_id__intelligence_handoffs__handoff_id__patch`
- `GET /api/f51/studio/crew/projects/{project_id}/intelligence/reasoning` :: `list_crew_reasoning_api_f51_studio_crew_projects__project_id__intelligence_reasoning_get`
- `GET /api/f51/studio/crew/projects/{project_id}/intelligence/reasoning/{reasoning_id}` :: `get_crew_reasoning_api_f51_studio_crew_projects__project_id__intelligence_reasoning__reasoning_id__get`
- `GET /api/f51/studio/crew/projects/{project_id}/needs-attention` :: `get_creative_attention_api_f51_studio_crew_projects__project_id__needs_attention_get`
- `GET /api/f51/studio/crew/projects/{project_id}/tasks` :: `get_project_tasks_api_f51_studio_crew_projects__project_id__tasks_get`
- `POST /api/f51/studio/crew/projects/{project_id}/tasks` :: `create_task_api_f51_studio_crew_projects__project_id__tasks_post`
- `POST /api/f51/studio/demo-project` :: `create_demo_project_api_f51_studio_demo_project_post`
- `POST /api/f51/studio/dev/seed-demo-project` :: `seed_demo_project_api_f51_studio_dev_seed_demo_project_post`
- `POST /api/f51/studio/emotion-analysis/projects/{project_id}/scenes/{scene_id}/analyze` :: `analyze_scene_emotion_api_f51_studio_emotion_analysis_projects__project_id__scenes__scene_id__analyze_post`
- `GET /api/f51/studio/exports/{project_id}/archive-snapshot` :: `export_archive_snapshot_api_f51_studio_exports__project_id__archive_snapshot_get`
- `GET /api/f51/studio/exports/{project_id}/cut-manifest` :: `export_cut_manifest_api_f51_studio_exports__project_id__cut_manifest_get`
- `GET /api/f51/studio/exports/{project_id}/festival-export` :: `export_festival_api_f51_studio_exports__project_id__festival_export_get`
- `GET /api/f51/studio/exports/{project_id}/pitch-pack` :: `export_pitch_pack_api_f51_studio_exports__project_id__pitch_pack_get`
- `GET /api/f51/studio/exports/{project_id}/prompt-pack` :: `export_prompt_pack_api_f51_studio_exports__project_id__prompt_pack_get`
- `GET /api/f51/studio/exports/{project_id}/shot-list` :: `export_shot_list_api_f51_studio_exports__project_id__shot_list_get`
- `GET /api/f51/studio/exports/{project_id}/subtitle-packages` :: `export_subtitles_api_f51_studio_exports__project_id__subtitle_packages_get`
- `GET /api/f51/studio/exports/{project_id}/teaser-export` :: `export_teaser_api_f51_studio_exports__project_id__teaser_export_get`
- `GET /api/f51/studio/exports/{project_id}/trailer-export` :: `export_trailer_api_f51_studio_exports__project_id__trailer_export_get`
- `GET /api/f51/studio/exports/{project_id}/youtube-export` :: `export_youtube_api_f51_studio_exports__project_id__youtube_export_get`
- `GET /api/f51/studio/memory/{project_id}` :: `get_project_memory_api_f51_studio_memory__project_id__get`
- `GET /api/f51/studio/memory/{project_id}/agent-context` :: `get_agent_context_api_f51_studio_memory__project_id__agent_context_get`
- `POST /api/f51/studio/memory/{project_id}/character` :: `update_character_memory_api_f51_studio_memory__project_id__character_post`
- `GET /api/f51/studio/memory/{project_id}/check-contradiction` :: `check_contradiction_api_f51_studio_memory__project_id__check_contradiction_get`
- `GET /api/f51/studio/memory/{project_id}/debug` :: `debug_memory_api_f51_studio_memory__project_id__debug_get`
- ... 335 more in runtime_openapi_inventory.json

## Memory
Count: 34

- `POST /api/f51/studio/memory/reference-analysis/delete` :: `delete_reference_memory_api_f51_studio_memory_reference_analysis_delete_post`
- `POST /api/f51/studio/memory/reference-analysis/retrieve` :: `retrieve_reference_memory_api_f51_studio_memory_reference_analysis_retrieve_post`
- `POST /api/f51/studio/memory/reference-analysis/store` :: `store_reference_analysis_api_f51_studio_memory_reference_analysis_store_post`
- `GET /api/f51/studio/memory/{project_id}` :: `get_project_memory_api_f51_studio_memory__project_id__get`
- `GET /api/f51/studio/memory/{project_id}/agent-context` :: `get_agent_context_api_f51_studio_memory__project_id__agent_context_get`
- `POST /api/f51/studio/memory/{project_id}/character` :: `update_character_memory_api_f51_studio_memory__project_id__character_post`
- `GET /api/f51/studio/memory/{project_id}/check-contradiction` :: `check_contradiction_api_f51_studio_memory__project_id__check_contradiction_get`
- `GET /api/f51/studio/memory/{project_id}/debug` :: `debug_memory_api_f51_studio_memory__project_id__debug_get`
- `POST /api/f51/studio/memory/{project_id}/init` :: `initialize_memory_api_f51_studio_memory__project_id__init_post`
- `POST /api/f51/studio/memory/{project_id}/review` :: `update_review_memory_api_f51_studio_memory__project_id__review_post`
- `POST /api/f51/studio/memory/{project_id}/scene` :: `update_scene_memory_api_f51_studio_memory__project_id__scene_post`
- `POST /api/f51/studio/memory/{project_id}/style` :: `update_style_memory_api_f51_studio_memory__project_id__style_post`
- `POST /api/f51/studio/memory/{project_id}/update` :: `update_project_memory_api_f51_studio_memory__project_id__update_post`
- `GET /api/f51/studio/memory/{project_id}/versions` :: `get_memory_versions_api_f51_studio_memory__project_id__versions_get`
- `POST /api/f51/studio/projects/{project_id}/build-memory` :: `build_project_cinematic_memory_api_f51_studio_projects__project_id__build_memory_post`
- `POST /api/f51/studio/projects/{project_id}/casting/memory-decisions` :: `save_casting_memory_decision_api_f51_studio_projects__project_id__casting_memory_decisions_post`
- `DELETE /api/f51/studio/projects/{project_id}/casting/memory-decisions/{decision_id}` :: `forget_casting_memory_decision_api_f51_studio_projects__project_id__casting_memory_decisions__decision_id__delete`
- `PATCH /api/f51/studio/projects/{project_id}/casting/memory-decisions/{decision_id}` :: `update_casting_memory_decision_api_f51_studio_projects__project_id__casting_memory_decisions__decision_id__patch`
- `POST /api/f51/studio/projects/{project_id}/creative-memories` :: `save_creative_decision_memory_api_f51_studio_projects__project_id__creative_memories_post`
- `DELETE /api/f51/studio/projects/{project_id}/creative-memories/{memory_id}` :: `delete_creative_decision_memory_api_f51_studio_projects__project_id__creative_memories__memory_id__delete`
- `PATCH /api/f51/studio/projects/{project_id}/creative-memories/{memory_id}` :: `update_creative_decision_memory_api_f51_studio_projects__project_id__creative_memories__memory_id__patch`
- `GET /api/f51/studio/projects/{project_id}/director-memory` :: `get_director_memory_api_f51_studio_projects__project_id__director_memory_get`
- `POST /api/f51/studio/projects/{project_id}/director-memory/scan` :: `scan_director_memory_api_f51_studio_projects__project_id__director_memory_scan_post`
- `GET /api/f51/studio/projects/{project_id}/director-memory/{kind}` :: `list_director_memory_entries_api_f51_studio_projects__project_id__director_memory__kind__get`
- `POST /api/f51/studio/projects/{project_id}/director-memory/{kind}` :: `save_director_memory_entry_api_f51_studio_projects__project_id__director_memory__kind__post`
- `DELETE /api/f51/studio/projects/{project_id}/director-memory/{kind}/{entry_id}` :: `delete_director_memory_entry_api_f51_studio_projects__project_id__director_memory__kind___entry_id__delete`
- `PATCH /api/f51/studio/projects/{project_id}/director-memory/{kind}/{entry_id}` :: `update_director_memory_entry_api_f51_studio_projects__project_id__director_memory__kind___entry_id__patch`
- `GET /api/f51/studio/projects/{project_id}/memory` :: `list_project_cinematic_memory_api_f51_studio_projects__project_id__memory_get`
- `POST /api/f51/studio/projects/{project_id}/search-memory` :: `search_project_cinematic_memory_api_f51_studio_projects__project_id__search_memory_post`
- `GET /api/f51/studio/scene-memory/search` :: `search_scene_memories_api_f51_studio_scene_memory_search_get`
- `GET /api/f51/studio/scene-memory/{memory_id}/related` :: `related_scene_memories_api_f51_studio_scene_memory__memory_id__related_get`
- `GET /api/f51/studio/video-assets/{asset_id}/scene-memory` :: `list_video_asset_scene_memory_api_f51_studio_video_assets__asset_id__scene_memory_get`
- `POST /api/f51/studio/video-assets/{asset_id}/scene-memory/ingest` :: `ingest_video_asset_scene_memory_api_f51_studio_video_assets__asset_id__scene_memory_ingest_post`
- `GET /api/f51/studio/video-keyframes/{keyframe_id}/related-memory` :: `related_memory_for_keyframe_api_f51_studio_video_keyframes__keyframe_id__related_memory_get`

## Continuity
Count: 7

- `POST /api/f51/studio/projects/{project_id}/analyze-continuity` :: `analyze_project_continuity_api_f51_studio_projects__project_id__analyze_continuity_post`
- `GET /api/f51/studio/projects/{project_id}/continuity-issues` :: `list_project_continuity_issues_api_f51_studio_projects__project_id__continuity_issues_get`
- `POST /api/f51/studio/projects/{project_id}/continuity/analyze` :: `analyze_project_continuity_legacy_api_f51_studio_projects__project_id__continuity_analyze_post`
- `GET /api/f51/studio/projects/{project_id}/continuity/issues` :: `list_project_continuity_issues_legacy_api_f51_studio_projects__project_id__continuity_issues_get`
- `POST /api/f51/studio/projects/{project_id}/scene-continuity-intelligence` :: `scene_continuity_intelligence_api_f51_studio_projects__project_id__scene_continuity_intelligence_post`
- `POST /api/f51/studio/storyboard-blueprints/{blueprint_id}/versions/{version_id}/continuity-review` :: `run_storyboard_continuity_review_api_f51_studio_storyboard_blueprints__blueprint_id__versions__version_id__continuity_review_post`
- `GET /api/projects/{project_id}/colorist/palette-continuity` :: `list_color_palette_continuity_api_projects__project_id__colorist_palette_continuity_get`
