"""
Provider Request Service - Phase 9.4

Builds a derived ProviderRenderRequest from a canonical SceneProductionPackage.
This service does NOT submit to providers, does NOT mutate the package, and does
NOT change any render flow. It only translates package fields into a
provider-facing request structure.

Design principles:
- Canonical package fields drive the request; derived guidance is advisory only.
- Provenance tracks which package fields were used for each request section.
- Sparse package fields produce minimal/empty requests, not errors.
- No provider-specific creative reinterpretation is applied.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from app.models.production_intelligence import (
    RenderExecutionRecord,
    RenderExecutionSummary,
    RenderExecutionState,
    ProviderRenderRequest,
    ProviderRequestProvenance,
    SceneProductionPackage,
)


class ProviderRequestService:
    """
    Derives a ProviderRenderRequest from a SceneProductionPackage.

    Phase 9.4: This is a read-only translation layer. It never mutates
    the package, never submits requests, and never influences runtime decisions.
    """

    def build_provider_request(
        self,
        scene_package: SceneProductionPackage,
        provider_name: str = "default",
        provider_capabilities: Optional[Dict[str, Any]] = None,
    ) -> ProviderRenderRequest:
        """
        Build a provider-specific render request from a scene package.

        This method translates canonical package fields and advisory guidance
        into a provider-ready request structure. It is explicitly derived —
        canonical package truth is never re-interpreted or mutated.

        Args:
            scene_package: The canonical SceneProductionPackage
            provider_name: Name of the target provider (e.g., "default", "openai")
            provider_capabilities: Optional provider-specific capability hints
                                  (e.g., supported param keys, aspect ratios)

        Returns:
            ProviderRenderRequest with derived prompt, exclusions, structured
            params, reference hints, execution notes, and provenance.
        """
        safe_caps = provider_capabilities if isinstance(provider_capabilities, dict) else {}
        adapter_payload = self.build_adapter_payload(
            scene_package=scene_package,
            provider_name=provider_name,
            provider_capabilities=safe_caps,
            advisory_context=None,
        )
        return self._build_provider_request_from_adapter_payload(adapter_payload)

    def build_execution_record(
        self,
        provider_request: ProviderRenderRequest,
        adapter_payload: Optional[Dict[str, Any]] = None,
        submission_state: str = "constructed",
    ) -> RenderExecutionRecord:
        """
        Build a bounded render execution record from provider request outputs.

        This record is observational only and does not affect execution authority.
        """
        safe_payload = adapter_payload if isinstance(adapter_payload, dict) else {}
        adapter_contract = safe_payload.get("adapter_contract")
        fingerprint: Optional[str] = None
        contract_version: Optional[str] = None
        provider_authority: Optional[str] = None
        advisory_authority: Optional[str] = None
        normalized_shape: Optional[str] = None

        if isinstance(adapter_contract, dict):
            raw_fingerprint = adapter_contract.get("payload_fingerprint")
            if isinstance(raw_fingerprint, str) and raw_fingerprint:
                fingerprint = raw_fingerprint
            raw_version = adapter_contract.get("version")
            if isinstance(raw_version, str) and raw_version:
                contract_version = raw_version
            raw_provider_authority = adapter_contract.get("provider_authority")
            if isinstance(raw_provider_authority, str) and raw_provider_authority:
                provider_authority = raw_provider_authority
            raw_advisory_authority = adapter_contract.get("advisory_authority")
            if isinstance(raw_advisory_authority, str) and raw_advisory_authority:
                advisory_authority = raw_advisory_authority

        normalized_output = safe_payload.get("provider_normalized_output")
        if isinstance(normalized_output, dict):
            raw_shape = normalized_output.get("shape")
            if isinstance(raw_shape, str) and raw_shape:
                normalized_shape = raw_shape

        # Fallback extraction from runtime provenance notes when adapter payload
        # is unavailable.
        if not fingerprint:
            for note in provider_request.provenance.notes:
                if isinstance(note, str) and note.startswith("adapter_contract.payload_fingerprint="):
                    candidate = note.split("=", 1)[1].strip()
                    if candidate:
                        fingerprint = candidate
                        break

        normalized_state = self._coerce_execution_state(submission_state)
        now = datetime.utcnow().isoformat() + "Z"
        return RenderExecutionRecord(
            execution_id=f"exec_{uuid4().hex}",
            scene_id=provider_request.scene_id,
            film_id=provider_request.film_id,
            provider_name=provider_request.provider_name,
            adapter_payload_fingerprint=fingerprint,
            submission_state=normalized_state.value,
            created_at=now,
            updated_at=now,
            inspection_metadata={
                "adapter_contract_version": contract_version,
                "provider_authority": provider_authority,
                "advisory_authority": advisory_authority,
                "provider_normalized_shape": normalized_shape,
                "inspection_only": True,
            },
            provenance_notes=[
                note for note in provider_request.provenance.notes if isinstance(note, str)
            ],
        )

    def transition_execution_record_state(
        self,
        execution_record: RenderExecutionRecord,
        new_state: str,
        inspection_note: Optional[str] = None,
        inspection_metadata: Optional[Dict[str, Any]] = None,
    ) -> RenderExecutionRecord:
        """
        Transition execution record state in a bounded observational lifecycle.

        This helper is non-authoritative and does not trigger execution decisions.
        """
        current_state = self._coerce_execution_state(execution_record.submission_state)
        target_state = self._coerce_execution_state(new_state)
        allowed = self._allowed_execution_state_transitions().get(current_state, set())
        if target_state != current_state and target_state not in allowed:
            raise ValueError(
                f"Invalid execution state transition: {current_state.value} -> {target_state.value}"
            )

        updated_metadata = dict(execution_record.inspection_metadata or {})
        updated_metadata["lifecycle_observational"] = True
        if isinstance(inspection_metadata, dict):
            updated_metadata.update(inspection_metadata)

        updated_notes = list(execution_record.provenance_notes or [])
        transition_note = f"execution_state.transition={current_state.value}->{target_state.value}"
        if transition_note not in updated_notes:
            updated_notes.append(transition_note)
        if isinstance(inspection_note, str) and inspection_note.strip():
            note_text = f"execution_state.note={inspection_note.strip()}"
            if note_text not in updated_notes:
                updated_notes.append(note_text)

        return execution_record.model_copy(
            update={
                "submission_state": target_state.value,
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "inspection_metadata": updated_metadata,
                "provenance_notes": updated_notes,
            }
        )

    def attach_execution_observed_facts(
        self,
        execution_record: RenderExecutionRecord,
        provider_job_id: Optional[str] = None,
        provider_status: Optional[str] = None,
        error_summary: Optional[str] = None,
        output_artifact_refs: Optional[List[str]] = None,
        external_timestamps: Optional[Dict[str, Any]] = None,
        inspection_note: Optional[str] = None,
    ) -> RenderExecutionRecord:
        """
        Attach bounded provider execution facts to an execution record.

        This is observational only and must not influence execution authority.
        """
        observed = dict(execution_record.observed_execution_facts or {})

        if isinstance(provider_job_id, str) and provider_job_id.strip():
            observed["provider_job_id"] = provider_job_id.strip()
        if isinstance(provider_status, str) and provider_status.strip():
            observed["provider_status"] = provider_status.strip()
        if isinstance(error_summary, str) and error_summary.strip():
            observed["error_summary"] = error_summary.strip()

        if isinstance(output_artifact_refs, list):
            observed["output_artifact_refs"] = [
                item for item in output_artifact_refs
                if isinstance(item, str) and item.strip()
            ]

        if isinstance(external_timestamps, dict):
            observed["external_timestamps"] = {
                str(key): str(value)
                for key, value in external_timestamps.items()
                if isinstance(key, str) and value is not None
            }

        updated_notes = list(execution_record.provenance_notes or [])
        attach_note = "execution_facts.attached=true"
        if attach_note not in updated_notes:
            updated_notes.append(attach_note)
        if isinstance(provider_status, str) and provider_status.strip():
            status_note = f"execution_facts.provider_status={provider_status.strip()}"
            if status_note not in updated_notes:
                updated_notes.append(status_note)
        if isinstance(inspection_note, str) and inspection_note.strip():
            note_text = f"execution_facts.note={inspection_note.strip()}"
            if note_text not in updated_notes:
                updated_notes.append(note_text)

        updated_metadata = dict(execution_record.inspection_metadata or {})
        updated_metadata["execution_facts_observational"] = True

        return execution_record.model_copy(
            update={
                "observed_execution_facts": observed,
                "updated_at": datetime.utcnow().isoformat() + "Z",
                "inspection_metadata": updated_metadata,
                "provenance_notes": updated_notes,
            }
        )

    def derive_execution_summary(
        self,
        execution_record: RenderExecutionRecord,
    ) -> RenderExecutionSummary:
        """
        Derive a bounded read-only execution summary from an execution record.

        This summary is observational only and does not influence execution flow.
        """
        observed = (
            execution_record.observed_execution_facts
            if isinstance(execution_record.observed_execution_facts, dict)
            else {}
        )
        artifacts = observed.get("output_artifact_refs")
        has_output_artifacts = isinstance(artifacts, list) and any(
            isinstance(item, str) and item.strip() for item in artifacts
        )
        provider_status = observed.get("provider_status")
        if not isinstance(provider_status, str) or not provider_status.strip():
            provider_status = None
        error_summary = observed.get("error_summary")
        has_error = isinstance(error_summary, str) and bool(error_summary.strip())

        metadata = (
            execution_record.inspection_metadata
            if isinstance(execution_record.inspection_metadata, dict)
            else {}
        )

        return RenderExecutionSummary(
            execution_id=execution_record.execution_id,
            provider_name=execution_record.provider_name,
            lifecycle_state=execution_record.submission_state,
            provider_status=provider_status,
            has_output_artifacts=has_output_artifacts,
            has_error=has_error,
            latest_updated_at=execution_record.updated_at,
            inspection_flags={
                "inspection_only": True,
                "lifecycle_observational": bool(metadata.get("lifecycle_observational")),
                "execution_facts_observational": bool(metadata.get("execution_facts_observational")),
                "provider_authority": metadata.get("provider_authority"),
                "advisory_authority": metadata.get("advisory_authority"),
            },
        )

    def _coerce_execution_state(self, value: Any) -> RenderExecutionState:
        if isinstance(value, RenderExecutionState):
            return value
        if isinstance(value, str):
            try:
                return RenderExecutionState(value)
            except ValueError as exc:
                raise ValueError(f"Invalid execution state: {value}") from exc
        raise ValueError(f"Invalid execution state type: {type(value).__name__}")

    def _allowed_execution_state_transitions(self) -> Dict[RenderExecutionState, set[RenderExecutionState]]:
        return {
            RenderExecutionState.CONSTRUCTED: {
                RenderExecutionState.SUBMITTED,
                RenderExecutionState.FAILED,
                RenderExecutionState.CANCELLED,
            },
            RenderExecutionState.SUBMITTED: {
                RenderExecutionState.COMPLETED,
                RenderExecutionState.FAILED,
                RenderExecutionState.CANCELLED,
            },
            RenderExecutionState.COMPLETED: set(),
            RenderExecutionState.FAILED: set(),
            RenderExecutionState.CANCELLED: set(),
        }

    def build_adapter_payload(
        self,
        scene_package: SceneProductionPackage,
        provider_name: str = "default",
        provider_capabilities: Optional[Dict[str, Any]] = None,
        advisory_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Build a deterministic adapter-boundary payload from bounded system outputs.

        Boundary contract:
        - `canonical_scene_data`: render-facing fields derived from canonical package inputs
        - `provider_config`: explicit provider selector/capabilities inputs only
        - `advisory_context`: optional fenced advisory/debug context (never authority)
        - `provenance`: audit trail for canonical + advisory derivation

        This method is foundation-only and does not submit, route, or execute providers.
        """
        safe_caps = provider_capabilities if isinstance(provider_capabilities, dict) else {}
        safe_pkg = self._to_dict(scene_package)
        request = self._build_provider_request_core(
            safe_pkg=safe_pkg,
            provider_name=provider_name,
            safe_caps=safe_caps,
        )
        request_dict = request.model_dump()
        canonical_scene_data = {
            "scene_id": request_dict.get("scene_id"),
            "film_id": request_dict.get("film_id"),
            "prompt": request_dict.get("prompt", ""),
            "prompt_components": list(request_dict.get("prompt_components") or []),
            "exclusions": request_dict.get("exclusions", ""),
            "exclusion_components": list(request_dict.get("exclusion_components") or []),
            "structured_params": dict(request_dict.get("structured_params") or {}),
            "reference_hints": list(request_dict.get("reference_hints") or []),
            "execution_notes": list(request_dict.get("execution_notes") or []),
        }
        provider_config = {
            "provider_name": provider_name,
            "provider_capabilities": dict(safe_caps),
        }
        advisory_context_payload = {
            "provider_request_advisory_shaping_notes": list(request_dict.get("advisory_shaping_notes") or []),
            "co_director": self._sanitize_codirector_advisory_context(advisory_context),
        }
        provenance_payload = dict(request_dict.get("provenance") or {})
        provider_normalized_output = self._build_provider_normalized_output(
            canonical_scene_data=canonical_scene_data,
            provider_config=provider_config,
        )

        return {
            "canonical_scene_data": canonical_scene_data,
            # Provider authority stays explicit here; advisory context cannot override it.
            "provider_config": provider_config,
            "advisory_context": advisory_context_payload,
            # Provider-specific normalized request shape for inspection/readiness only.
            "provider_normalized_output": provider_normalized_output,
            "provenance": provenance_payload,
            "adapter_contract": {
                "version": "phase11.v1",
                "provider_authority": "provider_config_only",
                "advisory_authority": "non_authoritative",
                "payload_fingerprint": self._build_adapter_payload_fingerprint(
                    canonical_scene_data=canonical_scene_data,
                    provider_config=provider_config,
                    advisory_context=advisory_context_payload,
                    provider_normalized_output=provider_normalized_output,
                    provenance=provenance_payload,
                ),
            },
            # Internal parity payload so runtime can preserve current request behavior.
            "_provider_request": request_dict,
        }

    # -------------------------------------------------------------------------
    # Internal derivation helpers
    # -------------------------------------------------------------------------

    def _to_dict(self, pkg: Any) -> Dict[str, Any]:
        """Convert a scene package to dict safely."""
        if hasattr(pkg, "model_dump"):
            return pkg.model_dump()
        if isinstance(pkg, dict):
            return pkg
        return {}

    def _build_provider_request_from_adapter_payload(
        self,
        adapter_payload: Dict[str, Any],
    ) -> ProviderRenderRequest:
        """Rebuild the runtime ProviderRenderRequest from an adapter payload."""
        raw = adapter_payload.get("_provider_request")
        if isinstance(raw, dict):
            request = ProviderRenderRequest(**raw)
            # Phase 11 bounded adoption: use normalized output for one narrow runtime path.
            self._apply_generic_normalized_output(
                request=request,
                provider_normalized_output=adapter_payload.get("provider_normalized_output"),
            )
            self._attach_adapter_contract_trace(
                request=request,
                adapter_contract=adapter_payload.get("adapter_contract"),
            )
            self._attach_provider_normalized_trace(
                request=request,
                provider_normalized_output=adapter_payload.get("provider_normalized_output"),
            )
            return request
        # Conservative fallback path; should not be hit in normal flow.
        canonical = adapter_payload.get("canonical_scene_data") or {}
        provider_config = adapter_payload.get("provider_config") or {}
        advisory = adapter_payload.get("advisory_context") or {}
        request = ProviderRenderRequest(
            scene_id=str(canonical.get("scene_id") or "unknown_scene"),
            film_id=str(canonical.get("film_id") or "unknown_film"),
            provider_name=str(provider_config.get("provider_name") or "default"),
            prompt=str(canonical.get("prompt") or ""),
            prompt_components=list(canonical.get("prompt_components") or []),
            exclusions=str(canonical.get("exclusions") or ""),
            exclusion_components=list(canonical.get("exclusion_components") or []),
            structured_params=dict(canonical.get("structured_params") or {}),
            reference_hints=list(canonical.get("reference_hints") or []),
            execution_notes=list(canonical.get("execution_notes") or []),
            advisory_shaping_notes=list(advisory.get("provider_request_advisory_shaping_notes") or []),
            provenance=ProviderRequestProvenance(**dict(adapter_payload.get("provenance") or {})),
        )
        self._attach_adapter_contract_trace(
            request=request,
            adapter_contract=adapter_payload.get("adapter_contract"),
        )
        self._attach_provider_normalized_trace(
            request=request,
            provider_normalized_output=adapter_payload.get("provider_normalized_output"),
        )
        return request

    def _apply_generic_normalized_output(
        self,
        request: ProviderRenderRequest,
        provider_normalized_output: Optional[Dict[str, Any]],
    ) -> None:
        """
        Apply provider_normalized_output to runtime request construction for generic path only.

        This is a narrowly bounded runtime adoption step and does not influence
        provider selection authority.
        """
        def _trace(note: str) -> None:
            if note not in request.provenance.notes:
                request.provenance.notes.append(note)

        if request.provider_name != "generic":
            _trace("provider_normalized.runtime_adoption=skipped_provider_mismatch")
            return
        if not isinstance(provider_normalized_output, dict):
            _trace("provider_normalized.runtime_adoption=skipped_missing_output")
            return
        if provider_normalized_output.get("shape") != "generic_video_v1":
            _trace("provider_normalized.runtime_adoption=skipped_shape_mismatch")
            return

        normalized_payload = provider_normalized_output.get("normalized_payload")
        if not isinstance(normalized_payload, dict):
            _trace("provider_normalized.runtime_adoption=skipped_missing_payload")
            return

        prompt = normalized_payload.get("prompt")
        assets = normalized_payload.get("assets")
        metadata = normalized_payload.get("metadata")
        if not isinstance(metadata, dict):
            metadata = {}
            _trace("provider_normalized.runtime_metadata=invalid_or_missing")

        if isinstance(prompt, str):
            request.prompt = prompt
        if isinstance(assets, list):
            request.reference_hints = [str(item) for item in assets if isinstance(item, str)]

        if "negative_prompt" in metadata:
            negative_prompt = metadata.get("negative_prompt")
            if isinstance(negative_prompt, str):
                request.exclusions = negative_prompt

        # Keep structured params scoped to non-negative-prompt metadata.
        request.structured_params = {
            str(k): v for k, v in metadata.items()
            if str(k) != "negative_prompt"
        }

        _trace("provider_normalized.runtime_adoption=generic_video_v1")

    def _build_provider_request_core(
        self,
        safe_pkg: Dict[str, Any],
        provider_name: str,
        safe_caps: Dict[str, Any],
    ) -> ProviderRenderRequest:
        """Core request derivation from package + provider config inputs."""
        provenance = ProviderRequestProvenance(
            scene_package_id=safe_pkg.get("scene_id", ""),
            scene_id=safe_pkg.get("scene_id", ""),
            film_id=safe_pkg.get("film_id", ""),
        )

        prompt_components, provenance = self._derive_prompt(
            safe_pkg=safe_pkg,
            safe_caps=safe_caps,
            provenance=provenance,
        )
        exclusions, exclusion_components, provenance = self._derive_exclusions(
            safe_pkg=safe_pkg,
            provenance=provenance,
        )
        structured_params, provenance = self._derive_structured_params(
            safe_pkg=safe_pkg,
            safe_caps=safe_caps,
            provenance=provenance,
        )
        reference_hints, provenance = self._derive_reference_hints(
            safe_pkg=safe_pkg,
            provenance=provenance,
        )
        execution_notes, provenance = self._derive_execution_notes(
            safe_pkg=safe_pkg,
            provenance=provenance,
        )
        advisory_notes, provenance = self._derive_advisory_shaping_notes(
            safe_pkg=safe_pkg,
            provenance=provenance,
        )

        prompt = ", ".join(filter(None, prompt_components))
        exclusions_text = ", ".join(filter(None, exclusion_components))

        return ProviderRenderRequest(
            scene_id=safe_pkg.get("scene_id", "unknown_scene"),
            film_id=safe_pkg.get("film_id", "unknown_film"),
            provider_name=provider_name,
            prompt=prompt,
            prompt_components=[c for c in prompt_components if c],
            exclusions=exclusions_text,
            exclusion_components=[c for c in exclusion_components if c],
            structured_params=structured_params,
            reference_hints=reference_hints,
            execution_notes=execution_notes,
            advisory_shaping_notes=advisory_notes,
            provenance=provenance,
        )

    def _sanitize_codirector_advisory_context(
        self,
        advisory_context: Optional[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Fence optional Co-Director context into a minimal advisory-only debug shape.

        Any missing or malformed context returns None. This context is never used
        for provider routing or selection.
        """
        if not isinstance(advisory_context, dict):
            return None

        raw_context = advisory_context.get("co_director")
        if not isinstance(raw_context, dict):
            return None

        allowed_keys = [
            "mode",
            "workflow_active",
            "critique",
            "proposal",
            "comparison",
            "intensity",
        ]
        result: Dict[str, Any] = {}
        for key in allowed_keys:
            if key in raw_context:
                result[key] = raw_context.get(key)

        return result or None

    def _build_adapter_payload_fingerprint(
        self,
        canonical_scene_data: Dict[str, Any],
        provider_config: Dict[str, Any],
        advisory_context: Dict[str, Any],
        provider_normalized_output: Dict[str, Any],
        provenance: Dict[str, Any],
    ) -> str:
        """
        Build a deterministic fingerprint for adapter payload inspection.

        Excludes request timestamps/IDs by design so equivalent inputs yield
        stable fingerprints across repeated constructions.
        """
        normalized = {
            "canonical_scene_data": canonical_scene_data,
            "provider_config": provider_config,
            "advisory_context": advisory_context,
            "provider_normalized_output": provider_normalized_output,
            "provenance": provenance,
        }
        serialized = json.dumps(normalized, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def _build_provider_normalized_output(
        self,
        canonical_scene_data: Dict[str, Any],
        provider_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Build provider-specific normalized request shape for inspection readiness.

        This output is non-authoritative and does not influence runtime provider behavior.
        """
        provider_name = str(provider_config.get("provider_name") or "default").lower()
        prompt = str(canonical_scene_data.get("prompt") or "")
        exclusions = str(canonical_scene_data.get("exclusions") or "")
        reference_hints = list(canonical_scene_data.get("reference_hints") or [])
        structured_params = dict(canonical_scene_data.get("structured_params") or {})

        if provider_name == "higgsfield":
            normalized_payload = {
                "prompt": prompt,
                "reference_assets": reference_hints,
                "parameters": structured_params,
                "negative_prompt": exclusions,
            }
            shape = "higgsfield_v1"
        elif provider_name == "generic":
            normalized_payload = {
                "prompt": prompt,
                "assets": reference_hints,
                "metadata": {
                    **structured_params,
                    "negative_prompt": exclusions,
                },
            }
            shape = "generic_video_v1"
        elif provider_name == "openai":
            normalized_payload = {
                "input": prompt,
                "references": reference_hints,
                "config": {
                    **structured_params,
                    "negative_prompt": exclusions,
                },
            }
            shape = "openai_video_v1"
        else:
            normalized_payload = {
                "prompt": prompt,
                "reference_hints": reference_hints,
                "structured_params": structured_params,
                "negative_prompt": exclusions,
            }
            shape = "default_v1"

        return {
            "provider_name": provider_name,
            "shape": shape,
            "normalized_payload": normalized_payload,
            "inspection_only": True,
        }

    def _attach_adapter_contract_trace(
        self,
        request: ProviderRenderRequest,
        adapter_contract: Optional[Dict[str, Any]],
    ) -> None:
        """
        Attach adapter contract inspection trace to provenance notes.

        This is trace-only metadata and must never affect provider authority.
        """
        if not isinstance(adapter_contract, dict):
            return

        trace_lines: List[str] = []
        version = adapter_contract.get("version")
        provider_authority = adapter_contract.get("provider_authority")
        advisory_authority = adapter_contract.get("advisory_authority")
        payload_fingerprint = adapter_contract.get("payload_fingerprint")

        if isinstance(version, str) and version:
            trace_lines.append(f"adapter_contract.version={version}")
        if isinstance(provider_authority, str) and provider_authority:
            trace_lines.append(f"adapter_contract.provider_authority={provider_authority}")
        if isinstance(advisory_authority, str) and advisory_authority:
            trace_lines.append(f"adapter_contract.advisory_authority={advisory_authority}")
        if isinstance(payload_fingerprint, str) and payload_fingerprint:
            trace_lines.append(f"adapter_contract.payload_fingerprint={payload_fingerprint}")

        for line in trace_lines:
            if line not in request.provenance.notes:
                request.provenance.notes.append(line)

    def _attach_provider_normalized_trace(
        self,
        request: ProviderRenderRequest,
        provider_normalized_output: Optional[Dict[str, Any]],
    ) -> None:
        """
        Attach provider-normalized inspection trace to runtime provenance notes.

        This is runtime observability only and does not affect authority.
        """
        if not isinstance(provider_normalized_output, dict):
            return

        provider_name = provider_normalized_output.get("provider_name")
        shape = provider_normalized_output.get("shape")
        inspection_only = provider_normalized_output.get("inspection_only")

        trace_lines: List[str] = []
        if isinstance(provider_name, str) and provider_name:
            trace_lines.append(f"provider_normalized.provider_name={provider_name}")
        if isinstance(shape, str) and shape:
            trace_lines.append(f"provider_normalized.shape={shape}")
        if isinstance(inspection_only, bool):
            trace_lines.append(f"provider_normalized.inspection_only={str(inspection_only).lower()}")

        for line in trace_lines:
            if line not in request.provenance.notes:
                request.provenance.notes.append(line)

    def _derive_prompt(
        self,
        safe_pkg: Dict[str, Any],
        safe_caps: Dict[str, Any],
        provenance: ProviderRequestProvenance,
    ) -> tuple[List[str], ProviderRequestProvenance]:
        """
        Derive the main positive prompt from canonical package fields.

        Sources (canonical priority):
        1. visual_target — direct visual description
        2. emotional_target — tone/style intent
        3. narrative_purpose — story intent

        Advisory (low-weight):
        - cinematic_language: restraint_score, visual_intent (if strong signal)
        """
        components: List[str] = []
        provenance.prompt_sources = []
        provenance.advisory_sources = []

        # Canonical sources
        visual_target = str(safe_pkg.get("visual_target", "")).strip()
        if visual_target:
            components.append(visual_target)
            provenance.prompt_sources.append("visual_target")

        emotional_target = str(safe_pkg.get("emotional_target", "")).strip()
        if emotional_target:
            components.append(emotional_target)
            provenance.prompt_sources.append("emotional_target")

        narrative_purpose = str(safe_pkg.get("narrative_purpose", "")).strip()
        if narrative_purpose:
            components.append(narrative_purpose)
            provenance.prompt_sources.append("narrative_purpose")

        # Advisory: cinematic language (only if strong signal)
        derived = safe_pkg.get("derived_guidance") or {}
        cinematic = derived.get("cinematic_language") or {}
        if isinstance(cinematic, dict):
            restraint_score = cinematic.get("restraint_score")
            if isinstance(restraint_score, (int, float)) and restraint_score >= 0.7:
                visual_intent = cinematic.get("visual_intent")
                framing_meaning = cinematic.get("framing_meaning")
                if visual_intent and str(visual_intent) not in ("none_detected", ""):
                    components.append(f"cinematic intent: {visual_intent}")
                    provenance.advisory_sources.append("derived_guidance.cinematic_language.visual_intent")
                if framing_meaning and str(framing_meaning) not in ("neutral", ""):
                    components.append(f"framing: {framing_meaning}")
                    provenance.advisory_sources.append("derived_guidance.cinematic_language.framing_meaning")

        # Provider capability: append aspect ratio or format hints if available
        preferred_format = safe_caps.get("preferred_format", "")
        if preferred_format and isinstance(preferred_format, str):
            components.append(preferred_format)

        # Intent-aware append-only prompt shaping (Phase 19.1).
        # Never replaces canonical prompt content; only appends at the end.
        components.extend(self._derive_scene_intent_prompt_appendix(safe_pkg))

        if not provenance.prompt_sources:
            provenance.notes.append("No canonical prompt sources available; request is sparse.")

        return components, provenance

    def _derive_scene_intent_prompt_appendix(self, safe_pkg: Dict[str, Any]) -> List[str]:
        """
        Derive append-only prompt lines from scene intent metadata.

        Deterministic behavior:
        - Known label: append scene intent line + mapped guidance line.
        - Unknown label: append scene intent line only.
        - Missing/invalid label: append nothing.
        """
        label: Optional[str] = None

        execution_summary = safe_pkg.get("execution_summary")
        if isinstance(execution_summary, dict):
            scene_intent = execution_summary.get("scene_intent")
            if isinstance(scene_intent, dict):
                raw_label = scene_intent.get("label")
                if isinstance(raw_label, str):
                    trimmed = raw_label.strip()
                    if trimmed:
                        label = trimmed

        if label is None:
            scene_intent_root = safe_pkg.get("scene_intent")
            if isinstance(scene_intent_root, dict):
                raw_label = scene_intent_root.get("label")
                if isinstance(raw_label, str):
                    trimmed = raw_label.strip()
                    if trimmed:
                        label = trimmed

        metadata = safe_pkg.get("metadata")
        if label is None and isinstance(metadata, dict):
            metadata_scene_intent = metadata.get("scene_intent")
            if isinstance(metadata_scene_intent, dict):
                raw_label = metadata_scene_intent.get("label")
                if isinstance(raw_label, str):
                    trimmed = raw_label.strip()
                    if trimmed:
                        label = trimmed

        if label is None and isinstance(metadata, dict):
            raw_label = metadata.get("scene_intent_label")
            if isinstance(raw_label, str):
                trimmed = raw_label.strip()
                if trimmed:
                    label = trimmed

        if not label:
            return []

        lines: List[str] = [f"Scene intent: {label}."]
        if label.strip().lower() == "quiet emotional moment":
            lines.append(
                "Intent guidance: Favor restrained pacing, minimal movement, subtle expression, and atmospheric tension."
            )

        return lines

    def _derive_exclusions(
        self,
        safe_pkg: Dict[str, Any],
        provenance: ProviderRequestProvenance,
    ) -> tuple[List[str], List[str], ProviderRequestProvenance]:
        """
        Derive negative prompt / exclusion guidance from canonical package fields.

        Sources:
        - forbidden_moves — explicit hard exclusions
        - restraint_rules — soft do-not-do guidance
        """
        exclusion_components: List[str] = []
        provenance.negative_prompt_sources = []

        # Hard exclusions from forbidden_moves
        forbidden = safe_pkg.get("forbidden_moves") or []
        if isinstance(forbidden, list):
            for move in forbidden:
                if move and str(move).strip():
                    exclusion_components.append(f"no {str(move).strip()}")
                    provenance.negative_prompt_sources.append("forbidden_moves")

        # Soft exclusions from restraint_rules (low-weight)
        restraints = safe_pkg.get("restraint_rules") or []
        if isinstance(restraints, list):
            for rule in restraints:
                if rule and str(rule).strip():
                    # Deduplicate against forbidden_moves
                    if str(rule).strip().lower() not in [
                        str(m).lower() for m in (forbidden or [])
                    ]:
                        exclusion_components.append(str(rule).strip())
                        provenance.negative_prompt_sources.append("restraint_rules")

        if not provenance.negative_prompt_sources:
            provenance.notes.append("No exclusion sources found; no exclusions will be set.")

        return exclusion_components, exclusion_components, provenance

    def _derive_structured_params(
        self,
        safe_pkg: Dict[str, Any],
        safe_caps: Dict[str, Any],
        provenance: ProviderRequestProvenance,
    ) -> tuple[Dict[str, object], ProviderRequestProvenance]:
        """
        Derive structured parameters from visual_target and package fields.

        These are provider-interpretable parameter hints (e.g., aspect ratio,
        style preset, seed hints) derived from visual_target and capabilities.
        """
        params: Dict[str, object] = {}
        provenance.structured_params_sources = []

        # Extract style hints from visual_target if available
        visual_target = str(safe_pkg.get("visual_target", "")).strip()
        if visual_target:
            provenance.structured_params_sources.append("visual_target")

        # Derive aspect ratio hint from provider capabilities if not in visual_target
        aspect_ratio = safe_caps.get("default_aspect_ratio", "")
        if aspect_ratio and isinstance(aspect_ratio, str):
            params["aspect_ratio"] = aspect_ratio

        # Derive style preset from cinematic_language if strong signal
        derived = safe_pkg.get("derived_guidance") or {}
        cinematic = derived.get("cinematic_language") or {}
        if isinstance(cinematic, dict):
            restraint_score = cinematic.get("restraint_score")
            if isinstance(restraint_score, (int, float)) and restraint_score >= 0.7:
                provenance.structured_params_sources.append(
                    "derived_guidance.cinematic_language"
                )

        return params, provenance

    def _derive_reference_hints(
        self,
        safe_pkg: Dict[str, Any],
        provenance: ProviderRequestProvenance,
    ) -> tuple[List[str], ProviderRequestProvenance]:
        """
        Derive visual/thematic reference hints from motif_obligations.

        Motif obligations are canonical scene requirements — they are promoted
        to reference hints so the provider understands what to reinforce visually.
        """
        hints: List[str] = []
        provenance.reference_hint_sources = []

        motif_obligations = safe_pkg.get("motif_obligations") or []
        if isinstance(motif_obligations, list):
            for obligation in motif_obligations:
                if obligation and str(obligation).strip():
                    hints.append(str(obligation).strip())
                    provenance.reference_hint_sources.append("motif_obligations")

        if not provenance.reference_hint_sources:
            provenance.notes.append("No motif obligations found; no reference hints will be set.")

        return hints, provenance

    def _derive_execution_notes(
        self,
        safe_pkg: Dict[str, Any],
        provenance: ProviderRequestProvenance,
    ) -> tuple[List[str], ProviderRequestProvenance]:
        """
        Derive execution guidance notes from continuity_constraints.

        These are guidance notes for the render execution that do not
        mutate canonical package truth — they are advisory reminders.
        """
        notes: List[str] = []
        provenance.execution_notes_sources = []

        continuity_constraints = safe_pkg.get("continuity_constraints") or []
        if isinstance(continuity_constraints, list):
            for constraint in continuity_constraints:
                if constraint and str(constraint).strip():
                    notes.append(str(constraint).strip())
                    provenance.execution_notes_sources.append("continuity_constraints")

        if not provenance.execution_notes_sources:
            provenance.notes.append(
                "No continuity constraints found; no execution notes will be set."
            )

        return notes, provenance

    def _derive_advisory_shaping_notes(
        self,
        safe_pkg: Dict[str, Any],
        provenance: ProviderRequestProvenance,
    ) -> tuple[List[str], ProviderRequestProvenance]:
        """
        Derive advisory shaping notes from derived guidance (taste, cinematic language).

        These notes are explicitly labeled as non-canonical and carry advisory
        weight only. They do not override or reinterpret canonical package fields.

        Taste context (if present) remains low-weight as specified.
        """
        advisory_notes: List[str] = []
        provenance.advisory_sources = []

        derived = safe_pkg.get("derived_guidance") or {}
        if not isinstance(derived, dict):
            provenance.notes.append("No derived guidance available; no advisory shaping notes.")
            return advisory_notes, provenance

        # Taste guidance (low-weight advisory)
        taste = derived.get("taste_guidance") or {}
        if isinstance(taste, dict):
            dimension_adjustments = taste.get("dimension_adjustments") or {}
            if isinstance(dimension_adjustments, dict) and dimension_adjustments:
                for dimension, adjustment in dimension_adjustments.items():
                    if isinstance(adjustment, (int, float)) and abs(adjustment) > 0.0:
                        # Only surface meaningful taste signals
                        direction = "favor" if adjustment > 0 else "restrain"
                        advisory_notes.append(
                            f"[advisory/taste] {direction} {dimension} "
                            f"(weight={adjustment:.2f}, advisory only)"
                        )
                        if (
                            "derived_guidance.taste_guidance.dimension_adjustments"
                            not in provenance.advisory_sources
                        ):
                            provenance.advisory_sources.append(
                                "derived_guidance.taste_guidance.dimension_adjustments"
                            )

        # Cinematic language guidance (medium advisory)
        cinematic = derived.get("cinematic_language") or {}
        if isinstance(cinematic, dict):
            # Visual intent
            visual_intent = cinematic.get("visual_intent")
            if visual_intent and str(visual_intent) not in ("none_detected", ""):
                advisory_notes.append(f"[advisory/cinematic] visual intent: {visual_intent}")
                if (
                    "derived_guidance.cinematic_language.visual_intent"
                    not in provenance.advisory_sources
                ):
                    provenance.advisory_sources.append(
                        "derived_guidance.cinematic_language.visual_intent"
                    )

            # Motif evolution
            motif_evolution = cinematic.get("motif_evolution")
            if motif_evolution and str(motif_evolution) not in ("none", ""):
                advisory_notes.append(f"[advisory/cinematic] motif evolution: {motif_evolution}")
                provenance.advisory_sources.append(
                    "derived_guidance.cinematic_language.motif_evolution"
                )

        if not provenance.advisory_sources:
            provenance.notes.append(
                "No advisory shaping notes available; request is grounded in canonical fields only."
            )

        return advisory_notes, provenance

    def derive_execution_timeline(
        self,
        execution_records: List[RenderExecutionRecord],
    ) -> ExecutionTimeline:
        """
        Derive a bounded execution timeline from existing execution records.

        Phase 12: This method builds a read-only ExecutionTimeline from
        RenderExecutionRecord instances. It is observational only and
        does not control execution, trigger retries, or influence provider
        selection.

        Bounded fields:
        - event_type: from submission_state
        - provider_name: from explicit provider config (not advisory)
        - lifecycle_transition: from state transitions
        - provider_status: from observed_execution_facts
        - error presence: from observed_execution_facts.error_summary
        - artifact presence: from observed_execution_facts.output_artifact_refs
        - timestamp: from created_at/updated_at

        Args:
            execution_records: List of RenderExecutionRecord instances
                              (can be empty)

        Returns:
            ExecutionTimeline with derived events and summary
        """
        from app.models.production_intelligence import (
            ExecutionTimeline,
            ExecutionTimelineEvent,
        )
        from uuid import uuid4

        if not execution_records:
            return ExecutionTimeline(
                scene_id="",
                film_id="",
                timeline_id=f"tl_{uuid4().hex}",
                provenance_notes=["No execution records provided"],
            )

        # Sort records by created_at to ensure chronological order
        sorted_records = sorted(
            execution_records,
            key=lambda r: r.created_at or "",
        )

        # Derive scene_id and film_id from first record
        first_record = sorted_records[0]
        scene_id = first_record.scene_id
        film_id = first_record.film_id

        events: List[ExecutionTimelineEvent] = []
        previous_state: Optional[str] = None
        has_errors = False
        has_artifacts = False

        for idx, record in enumerate(sorted_records):
            # Extract event type from submission_state
            event_type = record.submission_state

            # Extract provider name (from explicit config, not advisory)
            provider_name = record.provider_name

            # Derive lifecycle transition if this is not the first record
            lifecycle_transition = None
            if previous_state is not None and previous_state != event_type:
                lifecycle_transition = f"{previous_state}->{event_type}"

            # Extract provider status from observed execution facts
            observed = (
                record.observed_execution_facts
                if isinstance(record.observed_execution_facts, dict)
                else {}
            )
            provider_status = observed.get("provider_status")
            if not isinstance(provider_status, str) or not provider_status.strip():
                provider_status = None

            # Determine error presence
            error_summary = observed.get("error_summary")
            event_has_error = (
                isinstance(error_summary, str) and bool(error_summary.strip())
            )
            if event_has_error:
                has_errors = True

            # Determine artifact presence
            output_artifact_refs = observed.get("output_artifact_refs")
            event_has_artifact = (
                isinstance(output_artifact_refs, list)
                and any(
                    isinstance(item, str) and item.strip()
                    for item in output_artifact_refs
                )
            )
            if event_has_artifact:
                has_artifacts = True

            # Use updated_at as the event timestamp (represents most recent state)
            timestamp = record.updated_at or record.created_at

            event = ExecutionTimelineEvent(
                event_type=event_type,
                provider_name=provider_name,
                lifecycle_transition=lifecycle_transition,
                provider_status=provider_status,
                has_error=event_has_error,
                has_artifact=event_has_artifact,
                timestamp=timestamp,
                event_index=idx,
            )
            events.append(event)

            previous_state = event_type

        # Build provenance notes
        provenance_notes = [
            f"timeline.derived_from={len(sorted_records)} execution records",
            "timeline.observational_only=true",
            "timeline.control_authority=false",
        ]

        timeline_metadata = {
            "derived_from_execution_records": True,
            "record_count": len(sorted_records),
        }

        return ExecutionTimeline(
            scene_id=scene_id,
            film_id=film_id,
            timeline_id=f"tl_{uuid4().hex}",
            events=events,
            event_count=len(events),
            has_errors=has_errors,
            has_artifacts=has_artifacts,
            timeline_metadata=timeline_metadata,
            provenance_notes=provenance_notes,
        )


# Global singleton
provider_request_service = ProviderRequestService()
