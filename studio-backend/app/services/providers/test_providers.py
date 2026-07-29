import copy
import inspect
import json
import socket
from pathlib import Path

import pytest
import app.services.render_executor as render_executor
import app.services.providers.execution_layer as provider_execution_layer
import app.services.providers.comfyui_provider as comfyui_provider
from app.services.providers.real_provider_adapter import execute_real_image_render
from app.services.providers.local_image_provider import execute_local_image_render
from app.services.providers.video_provider import (
    build_video_render_payload,
    submit_video_render,
    normalize_video_result,
)
from app.services.providers.comfyui_provider import (
    derive_deterministic_seed,
    detect_workflow_format,
    validate_comfyui_api_workflow,
)

from app.services.providers import (
    MockProvider,
    ProviderRegistry,
    RealProviderStub,
    RenderProvider,
    build_manual_provider_selection_contract,
    build_provider_config_snapshot,
    build_provider_capability,
    build_execution_context,
    build_provider_selection_state,
    normalize_selection_request,
    resolve_provider_selection,
    build_provider_readiness_summary,
    build_provider_safety_contract,
    build_default_registry,
    build_provider_failure,
    build_provider_selection_audit,
    execute_provider_render,
    get_default_capabilities,
    get_provider_credential_state,
    get_provider_config,
    is_provider_config_enabled,
    is_provider_enabled,
    normalize_provider_failure,
    normalize_provider_result,
    resolve_default_provider,
    select_provider_with_audit,
    validate_provider_payload,
)
from app.services.providers.config_surface import (
    build_credential_validation_summary,
    build_provider_activation_contract,
    build_provider_activation_state,
    build_provider_config_validation,
    build_provider_enablement_gate,
    build_provider_intent_signal,
    build_provider_registry_snapshot,
    build_provider_safety_summary,
)
from app.services.script_parser import ScriptParser


def test_render_provider_interface_contract_exists():
    provider = MockProvider()
    assert isinstance(provider, RenderProvider)
    assert hasattr(provider, "render")
    assert hasattr(provider, "execute")


def test_validate_provider_payload_accepts_valid_payload():
    payload = {
        "shot_id": "shot_scene_001_001",
        "prompt": {
            "base_intent": "Opening line",
            "visual_tokens": [],
            "shot_tokens": [],
        },
    }
    assert validate_provider_payload(payload) is True


def test_validate_provider_payload_rejects_malformed_payload_safely():
    assert validate_provider_payload(None) is False
    assert validate_provider_payload("bad") is False
    assert validate_provider_payload({}) is False
    assert validate_provider_payload({"shot_id": "", "prompt": {}}) is False
    assert validate_provider_payload({"shot_id": "shot_1", "prompt": None}) is False


def test_mock_provider_skipped_path():
    provider = MockProvider()

    assert provider.render({"shot_id": None, "prompt": None}) == {
        "render_id": None,
        "status": "not_executed",
        "provider": "mock",
        "error": None,
        "error_code": None,
        "meta": {"file_path": None, "url": None},
    }


def test_real_provider_blocked_when_runtime_flag_false_even_if_real_enabled_and_credentials_present():
    result = execute_provider_render(
        provider_name="real_stub",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {}},
        config={
            "default_provider": "real_stub",
            "enabled_providers": ["mock", "real_stub"],
            "real_enabled": True,
            "real_provider_runtime_flag": False,
            "provider_credentials": {"real_stub": {"credential": "***placeholder***"}},
        },
    )
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "real_stub",
        "error": "Real provider execution locked",
        "error_code": "real_provider_locked",
        "meta": {"file_path": None, "url": None},
    }


def test_real_provider_blocked_without_credentials_even_when_flags_true():
    result = execute_provider_render(
        provider_name="real_stub",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {}},
        config={
            "default_provider": "real_stub",
            "enabled_providers": ["mock", "real_stub"],
            "real_enabled": True,
            "real_provider_runtime_flag": True,
        },
    )
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "real_stub",
        "error": "Real provider execution locked",
        "error_code": "real_provider_locked",
        "meta": {"file_path": None, "url": None},
    }


def test_real_provider_executes_when_all_gates_true_with_normalized_meta():
    result = execute_provider_render(
        provider_name="real_stub",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {"base_intent": "x"}},
        config={
            "default_provider": "real_stub",
            "enabled_providers": ["mock", "real_stub"],
            "real_enabled": True,
            "real_provider_runtime_flag": True,
            "provider_credentials": {"real_stub": {"credential": "***placeholder***"}},
        },
    )
    assert result == {
        "render_id": "real_shot_scene_001_001",
        "status": "success",
        "provider": "real_stub",
        "error": None,
        "error_code": None,
        "meta": {
            "file_path": "/tmp/studio_renders/real_shot_scene_001_001.png",
            "url": None,
        },
    }


def test_real_provider_failure_is_safe_and_not_retried(monkeypatch):
    calls = {"count": 0}

    def _raise_once(prompt, shot_id):
        calls["count"] += 1
        raise RuntimeError("boom")

    monkeypatch.setitem(provider_execution_layer._DIRECT_PROVIDER_ADAPTERS, "real_stub", _raise_once)

    result = execute_provider_render(
        provider_name="real_stub",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {"base_intent": "x"}},
        config={
            "default_provider": "real_stub",
            "enabled_providers": ["mock", "real_stub"],
            "real_enabled": True,
            "real_provider_runtime_flag": True,
            "provider_credentials": {"real_stub": {"credential": "***placeholder***"}},
        },
    )

    assert calls["count"] == 1
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "real_stub",
        "error": "boom",
        "error_code": "provider_exception",
        "meta": {"file_path": None, "url": None},
    }


def test_real_provider_execution_deterministic_when_gates_true():
    config = {
        "default_provider": "real_stub",
        "enabled_providers": ["mock", "real_stub"],
        "real_enabled": True,
        "real_provider_runtime_flag": True,
        "provider_credentials": {"real_stub": {"credential": "***placeholder***"}},
    }
    payload = {"shot_id": "shot_scene_001_001", "prompt": {"base_intent": "x"}}

    first = execute_provider_render("real_stub", payload, config)
    second = execute_provider_render("real_stub", payload, config)
    assert first == second


def test_execute_render_sequence_respects_cap_order_and_continues_on_failure(monkeypatch):
    calls = []

    def _fake_execute_render(provider_name, provider_payload, config=None):
        calls.append((provider_name, provider_payload, config))
        shot_id = provider_payload.get("shot_id") if isinstance(provider_payload, dict) else "unknown"
        if shot_id == "shot_b":
            return {
                "render_id": None,
                "status": "failed",
                "provider": "real_stub",
                "error": "adapter_failed",
                "error_code": "adapter_failed",
                "meta": {"file_path": None, "url": None},
            }
        return {
            "render_id": f"real_{shot_id}",
            "status": "success",
            "provider": "real_stub",
            "error": None,
            "error_code": None,
            "meta": {"file_path": f"/tmp/{shot_id}.png", "url": None},
        }

    monkeypatch.setattr(provider_execution_layer, "execute_render", _fake_execute_render)
    payloads = [
        {"shot_id": "shot_a", "prompt": {"base_intent": "x"}},
        {"shot_id": "shot_b", "prompt": {"base_intent": "x"}},
        {"shot_id": "shot_c", "prompt": {"base_intent": "x"}},
        {"shot_id": "shot_d", "prompt": {"base_intent": "x"}},
    ]

    results = provider_execution_layer.execute_render_sequence(
        "real_stub",
        payloads,
        {"real_enabled": True},
        max_shots=3,
    )

    assert len(calls) == 3
    assert [call[1]["shot_id"] for call in calls] == ["shot_a", "shot_b", "shot_c"]
    assert len(results) == 3
    assert results[0]["status"] == "success"
    assert results[1]["status"] == "failed"
    assert results[2]["status"] == "success"
    assert all(isinstance(result.get("meta"), dict) for result in results)


def test_execute_render_sequence_respects_min_of_planned_and_cap(monkeypatch):
    calls = []

    def _fake_execute_render(provider_name, provider_payload, config=None):
        calls.append((provider_name, provider_payload, config))
        shot_id = provider_payload.get("shot_id") if isinstance(provider_payload, dict) else "unknown"
        return {
            "render_id": f"real_{shot_id}",
            "status": "success",
            "provider": "real_stub",
            "error": None,
            "error_code": None,
            "meta": {"file_path": f"/tmp/{shot_id}.png", "url": None},
        }

    monkeypatch.setattr(provider_execution_layer, "execute_render", _fake_execute_render)
    payloads = [
        {"shot_id": "shot_1", "prompt": {"base_intent": "x"}},
        {"shot_id": "shot_2", "prompt": {"base_intent": "x"}},
    ]

    results = provider_execution_layer.execute_render_sequence(
        "real_stub",
        payloads,
        {"real_enabled": True},
        max_shots=3,
    )

    assert len(calls) == 2
    assert [call[1]["shot_id"] for call in calls] == ["shot_1", "shot_2"]
    assert len(results) == 2


def test_execute_render_sequence_is_synchronous_and_non_retrying_by_contract():
    source = inspect.getsource(provider_execution_layer.execute_render_sequence)
    assert "async def" not in source
    assert "retry" not in source.lower()


def test_mock_provider_success_path():
    provider = MockProvider()

    result = provider.render(
        {
            "shot_id": "shot_scene_001_001",
            "prompt": {"base_intent": "Opening line", "visual_tokens": [], "shot_tokens": []},
        }
    )
    assert result == {
        "render_id": "mock_shot_scene_001_001",
        "status": "success",
        "provider": "mock",
        "error": None,
        "error_code": None,
        "meta": {"file_path": None, "url": None},
    }


def test_video_provider_missing_api_key_does_not_crash():
    payload = build_video_render_payload(
        {"scene_id": "scene_001", "heading": "INT. ROOM - NIGHT"},
        {"shot_id": "shot_001"},
        {"base_prompt": "test"},
    )
    result = submit_video_render(
        payload,
        {
            "video_provider_enabled": True,
            "video_provider_name": "external_video",
            "video_provider_api_key": "",
            "video_provider_base_url": "https://example.invalid",
        },
    )
    normalized = normalize_video_result(result)
    assert normalized["status"] == "failed"
    assert normalized["video_url"] is None
    assert normalized["thumbnail_url"] is None
    assert isinstance(normalized["error"], str)


def test_video_provider_normalized_shape_stable():
    normalized = normalize_video_result(
        {
            "render_id": "video_scene_001_shot_001",
            "status": "pending",
            "provider": "external_video",
            "video_url": None,
            "thumbnail_url": "https://example.invalid/thumb.jpg",
            "error": None,
            "meta": {"queue_position": 1},
        }
    )
    assert normalized == {
        "render_id": "video_scene_001_shot_001",
        "status": "pending",
        "provider": "external_video",
        "video_url": None,
        "thumbnail_url": "https://example.invalid/thumb.jpg",
        "error": None,
        "meta": {"queue_position": 1},
    }


def test_provider_registry_registers_and_retrieves_provider():
    registry = ProviderRegistry()
    provider = MockProvider()

    registry.register_provider("mock", provider)

    retrieved = registry.get_provider("mock")
    assert retrieved is provider


def test_provider_registry_unknown_provider_raises_controlled_value_error():
    registry = ProviderRegistry()

    with pytest.raises(ValueError, match="Unknown provider"):
        registry.get_provider("missing")


def test_default_registry_includes_mock_provider():
    registry = build_default_registry()

    provider = registry.get_provider("mock")
    assert isinstance(provider, MockProvider)


def test_real_stub_not_registered_by_default():
    registry = build_default_registry()
    with pytest.raises(ValueError, match="Unknown provider"):
        registry.get_provider("real_stub")


def test_real_stub_registered_only_when_explicitly_enabled():
    enabled_config = {
        "enabled_providers": ["mock", "real_stub"],
    }
    registry = build_default_registry(enabled_config)
    provider = registry.get_provider("real_stub")
    assert isinstance(provider, RealProviderStub)


def test_provider_config_deterministic(monkeypatch):
    monkeypatch.delenv("RUNWAYML_API_SECRET", raising=False)
    monkeypatch.delenv("RUNWAY_API_KEY", raising=False)
    monkeypatch.delenv("VIDEO_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("IMAGE_PROVIDER_API_KEY", raising=False)
    monkeypatch.delenv("RUNWAY_API_BASE_URL", raising=False)
    monkeypatch.delenv("VIDEO_PROVIDER_BASE_URL", raising=False)

    first = get_provider_config()
    second = get_provider_config()

    assert first == second
    first["enabled_providers"].append("other")
    assert get_provider_config() == {
        "default_provider": "mock",
        "enabled_providers": ["mock"],
        "quality_priority": "cinematic_quality",
        "image_provider_enabled": False,
        "image_provider_name": "",
        "image_provider_api_key": "",
        "image_provider_base_url": "",
        "comfyui_enabled": False,
        "comfyui_base_url": "http://127.0.0.1:8188",
        "comfyui_cfg": 7.0,
        "comfyui_steps": 25,
        "comfyui_width": 832,
        "comfyui_height": 468,
        "comfyui_seed_mode": "deterministic",
        "comfyui_motion_enabled": False,
        "comfyui_motion_workflow_path": "/Users/amberreed/ComfyUI/workflows/animate_diff_basic.json",
        "video_provider_enabled": False,
        "video_provider_name": "runway",
        "video_provider_api_key": "",
        "video_provider_base_url": "https://api.dev.runwayml.com",
        "runway_timeout_seconds": 60,
    }


def test_comfyui_deterministic_seed_is_stable():
    first = derive_deterministic_seed("scene_001", "shot_001", "dark farmhouse kitchen")
    second = derive_deterministic_seed("scene_001", "shot_001", "dark farmhouse kitchen")
    third = derive_deterministic_seed("scene_001", "shot_002", "dark farmhouse kitchen")
    assert isinstance(first, int)
    assert first == second
    assert first != third


def test_comfyui_validate_api_workflow_rejects_ui_format():
    ui_format = {
        "nodes": [],
        "links": [],
        "last_node_id": 9,
    }
    result = validate_comfyui_api_workflow(ui_format)
    assert result == {"valid": False, "reason": "comfyui_workflow_not_api_format"}


def test_comfyui_detect_workflow_format():
    ui_format = {"nodes": [], "links": [], "last_node_id": 9}
    api_format = {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}}}
    unknown_format = {"alpha": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}}}
    assert detect_workflow_format(ui_format) == "ui"
    assert detect_workflow_format(api_format) == "api"
    assert detect_workflow_format(unknown_format) == "unknown"


def test_comfyui_validate_api_workflow_accepts_api_format():
    api_format = {
        "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "x", "clip": ["2", 1]}},
        "2": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "dreamshaper.safetensors"}},
    }
    result = validate_comfyui_api_workflow(api_format)
    assert result == {"valid": True, "reason": "ok"}


def test_comfyui_validate_api_workflow_rejects_invalid_node_keys():
    invalid = {"alpha": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}}}
    result = validate_comfyui_api_workflow(invalid)
    assert result == {"valid": False, "reason": "comfyui_workflow_not_api_format"}


def test_comfyui_render_motion_parses_save_animated_webp_output(monkeypatch, tmp_path):
    workflow_path = tmp_path / "motion_workflow.json"
    workflow_path.write_text(
        json.dumps(
            {
                "prompt": {
                    "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}},
                    "2": {"class_type": "SaveAnimatedWEBP", "inputs": {}},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        comfyui_provider,
        "get_provider_config",
        lambda: {
            "comfyui_enabled": True,
            "comfyui_motion_enabled": True,
            "comfyui_base_url": "http://127.0.0.1:8188",
            "comfyui_motion_workflow_path": str(workflow_path),
        },
    )
    monkeypatch.setattr(
        comfyui_provider,
        "_post_json_with_detail",
        lambda *_args, **_kwargs: {"ok": True, "status_code": 200, "body": {"prompt_id": "pid_001"}},
    )
    monkeypatch.setattr(
        comfyui_provider,
        "_get_json",
        lambda *_args, **_kwargs: {
            "pid_001": {
                "outputs": {
                    "8": {
                        "animated": [
                            {"filename": "studio_motion_00001_.webp", "subfolder": "", "type": "output"}
                        ]
                    }
                }
            }
        },
    )
    monkeypatch.setattr(comfyui_provider.time, "sleep", lambda *_args, **_kwargs: None)

    result = comfyui_provider.render_motion("data:image/png;base64,AAAA", "slow dread")
    assert isinstance(result, dict)
    assert result == {
        "render_id": "comfyui_motion_pid_001",
        "status": "success",
        "provider": "comfyui_motion",
        "video_url": "http://127.0.0.1:8188/view?filename=studio_motion_00001_.webp&subfolder=&type=output",
        "thumbnail_url": None,
        "file_path": None,
        "error": None,
        "meta": {
            "prompt_id": "pid_001",
            "source": "image_to_motion",
            "format": "webp",
            "filename": "studio_motion_00001_.webp",
            "subfolder": "",
            "type": "output",
            "output_key": "animated",
        },
    }


def test_comfyui_render_motion_preserves_image_output_parsing(monkeypatch, tmp_path):
    workflow_path = tmp_path / "motion_workflow.json"
    workflow_path.write_text(
        json.dumps(
            {
                "prompt": {
                    "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}},
                    "2": {"class_type": "SaveAnimatedWEBP", "inputs": {}},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        comfyui_provider,
        "get_provider_config",
        lambda: {
            "comfyui_enabled": True,
            "comfyui_motion_enabled": True,
            "comfyui_base_url": "http://127.0.0.1:8188",
            "comfyui_motion_workflow_path": str(workflow_path),
        },
    )
    monkeypatch.setattr(
        comfyui_provider,
        "_post_json_with_detail",
        lambda *_args, **_kwargs: {"ok": True, "status_code": 200, "body": {"prompt_id": "pid_img"}},
    )
    monkeypatch.setattr(
        comfyui_provider,
        "_get_json",
        lambda *_args, **_kwargs: {
            "pid_img": {
                "outputs": {
                    "9": {
                        "images": [
                            {"filename": "frame_00001_.png", "subfolder": "motion", "type": "output"}
                        ]
                    }
                }
            }
        },
    )
    monkeypatch.setattr(comfyui_provider.time, "sleep", lambda *_args, **_kwargs: None)

    result = comfyui_provider.render_motion("data:image/png;base64,AAAA", "slow dread")
    assert isinstance(result, dict)
    assert result.get("video_url") == "http://127.0.0.1:8188/view?filename=frame_00001_.png&subfolder=motion&type=output"
    assert result.get("status") == "success"
    assert result.get("provider") == "comfyui_motion"
    assert isinstance(result.get("meta"), dict)
    assert result["meta"].get("format") == "png"


def test_comfyui_render_motion_returns_no_motion_output_error_when_history_has_no_media(monkeypatch, tmp_path):
    workflow_path = tmp_path / "motion_workflow.json"
    workflow_path.write_text(
        json.dumps(
            {
                "prompt": {
                    "1": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}},
                    "2": {"class_type": "SaveAnimatedWEBP", "inputs": {}},
                }
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        comfyui_provider,
        "get_provider_config",
        lambda: {
            "comfyui_enabled": True,
            "comfyui_motion_enabled": True,
            "comfyui_base_url": "http://127.0.0.1:8188",
            "comfyui_motion_workflow_path": str(workflow_path),
        },
    )
    monkeypatch.setattr(
        comfyui_provider,
        "_post_json_with_detail",
        lambda *_args, **_kwargs: {"ok": True, "status_code": 200, "body": {"prompt_id": "pid_none"}},
    )
    monkeypatch.setattr(
        comfyui_provider,
        "_get_json",
        lambda *_args, **_kwargs: {"pid_none": {"outputs": {"9": {"text": "no-media"}}}},
    )
    monkeypatch.setattr(comfyui_provider.time, "sleep", lambda *_args, **_kwargs: None)

    result = comfyui_provider.render_motion("data:image/png;base64,AAAA", "slow dread")
    assert result is None
    assert comfyui_provider.get_last_render_error() == "comfyui_no_motion_output"


def test_comfyui_render_motion_payload_failure_includes_server_response(monkeypatch, tmp_path):
    workflow_path = tmp_path / "motion_workflow.json"
    workflow_path.write_text(json.dumps({"prompt": {"1": {"class_type": "CLIPTextEncode", "inputs": {"text": "x"}}}}), encoding="utf-8")

    monkeypatch.setattr(
        comfyui_provider,
        "get_provider_config",
        lambda: {
            "comfyui_enabled": True,
            "comfyui_motion_enabled": True,
            "comfyui_base_url": "http://127.0.0.1:8188",
            "comfyui_motion_workflow_path": str(workflow_path),
        },
    )
    monkeypatch.setattr(
        comfyui_provider,
        "_post_json_with_detail",
        lambda *_args, **_kwargs: {
            "ok": False,
            "status_code": 400,
            "body": {"error": "Invalid node 8"},
            "error_message": "Bad Request",
        },
    )

    result = comfyui_provider.render_motion("data:image/png;base64,AAAA", "slow dread")
    assert result is None
    error = comfyui_provider.get_last_render_error()
    assert error.startswith("comfyui_payload_failed:400:")
    assert "Invalid node 8" in error


def test_mock_capability_exact_shape():
    assert build_provider_capability("mock") == {
        "provider": "mock",
        "enabled": True,
        "network_required": False,
        "supports_render": True,
        "supports_streaming": False,
        "supports_sync": True,
        "supports_multi_shot": False,
        "requires_credentials": False,
    }


def test_unknown_capability_disabled_shape():
    assert build_provider_capability("unknown_provider") == {
        "provider": "unknown_provider",
        "enabled": False,
        "network_required": False,
        "supports_render": False,
        "supports_streaming": False,
        "supports_sync": False,
        "supports_multi_shot": False,
        "requires_credentials": False,
    }


def test_default_capabilities_deterministic():
    first = get_default_capabilities()
    second = get_default_capabilities()
    assert first == second
    first["mock"]["enabled"] = False
    assert get_default_capabilities() == {
        "mock": {
            "provider": "mock",
            "enabled": True,
            "network_required": False,
            "supports_render": True,
            "supports_streaming": False,
            "supports_sync": True,
            "supports_multi_shot": False,
            "requires_credentials": False,
        },
        "local_image": {
            "provider": "local_image",
            "enabled": True,
            "network_required": False,
            "supports_render": True,
            "supports_streaming": False,
            "supports_sync": True,
            "supports_multi_shot": False,
            "requires_credentials": False,
        },
        "real_stub": {
            "provider": "real_stub",
            "enabled": False,
            "network_required": False,
            "supports_render": False,
            "supports_streaming": False,
            "supports_sync": False,
            "supports_multi_shot": False,
            "requires_credentials": True,
        }
    }


def test_real_stub_capability_enablement_depends_on_config():
    disabled = build_provider_capability("real_stub", get_provider_config())
    enabled = build_provider_capability(
        "real_stub",
        {"default_provider": "mock", "enabled_providers": ["mock", "real_stub"]},
    )

    assert disabled["enabled"] is False
    assert enabled["enabled"] is True
    assert enabled["supports_render"] is False


def test_provider_capability_deterministic_repeated_calls():
    config = {"default_provider": "mock", "enabled_providers": ["mock", "real_stub"]}
    first = build_provider_capability("real_stub", config)
    second = build_provider_capability("real_stub", config)
    assert first == second


def test_selection_audit_default_mock():
    audit = select_provider_with_audit(None, get_provider_config())
    assert audit == {
        "requested_provider": "mock",
        "selected_provider": "mock",
        "allowed": True,
        "reason": "Default provider selected",
        "fallback_used": False,
    }


def test_requested_enabled_provider_allowed():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "quality_priority": "cinematic_quality",
    }
    audit = select_provider_with_audit("real_stub", config)
    assert audit == {
        "requested_provider": "real_stub",
        "selected_provider": "real_stub",
        "allowed": True,
        "reason": "Requested provider enabled",
        "fallback_used": False,
    }


def test_disabled_or_unknown_provider_falls_back_to_mock_with_fallback_true():
    audit = select_provider_with_audit("unknown_provider", get_provider_config())
    assert audit == {
        "requested_provider": "unknown_provider",
        "selected_provider": "mock",
        "allowed": False,
        "reason": "Requested provider disabled",
        "fallback_used": True,
    }


def test_default_provider_resolves_to_mock():
    assert resolve_default_provider(get_provider_config()) == "mock"
    assert resolve_default_provider(None) == "mock"
    assert resolve_default_provider({"default_provider": "mock", "enabled_providers": []}) == "mock"


def test_enabled_provider_check_works():
    config = get_provider_config()

    assert is_provider_enabled("mock", config) is True
    assert is_provider_enabled("other", config) is False


def test_mock_credential_state_exact_shape():
    state = get_provider_credential_state("mock", get_provider_config())
    assert state == {
        "provider": "mock",
        "enabled": True,
        "credential_present": True,
        "credential_source": "none",
        "reason": "Mock provider does not require credentials",
    }


def test_real_or_unknown_provider_disabled_by_default():
    state = get_provider_credential_state("real_stub", get_provider_config())
    assert state == {
        "provider": "real_stub",
        "enabled": False,
        "credential_present": False,
        "credential_source": "none",
        "reason": "Provider disabled by config",
    }


def test_enabled_provider_with_env_credential_reports_presence_without_value(monkeypatch):
    monkeypatch.setenv("REAL_STUB_API_KEY", "super-secret-value")
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "provider_credentials": {
            "real_stub": {
                "env_var": "REAL_STUB_API_KEY",
            }
        },
    }
    state = get_provider_credential_state("real_stub", config)
    assert state == {
        "provider": "real_stub",
        "enabled": True,
        "credential_present": True,
        "credential_source": "env",
        "reason": "Provider credentials available",
    }
    dumped = json.dumps(state)
    assert "REAL_STUB_API_KEY" not in dumped
    assert "super-secret-value" not in dumped


def test_enabled_provider_with_config_placeholder_reports_presence_without_value():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "provider_credentials": {
            "real_stub": {
                "credential": "***placeholder***",
            }
        },
    }
    state = get_provider_credential_state("real_stub", config)
    assert state == {
        "provider": "real_stub",
        "enabled": True,
        "credential_present": True,
        "credential_source": "config_present",
        "reason": "Provider credentials available",
    }
    dumped = json.dumps(state)
    assert "***placeholder***" not in dumped


def test_malformed_config_falls_back_safely_for_credentials():
    state = get_provider_credential_state("real_stub", {"enabled_providers": "bad-shape"})
    assert state == {
        "provider": "real_stub",
        "enabled": False,
        "credential_present": False,
        "credential_source": "none",
        "reason": "Provider disabled by config",
    }


def test_is_provider_config_enabled_behavior():
    config = get_provider_config()
    assert is_provider_config_enabled("mock", config) is True
    assert is_provider_config_enabled("real_stub", config) is False


def test_no_key_material_in_credential_state_outputs():
    config = {
        "enabled_providers": ["mock", "real_stub"],
        "provider_credentials": {
            "real_stub": {
                "api_key": "ultra-secret",
                "token": "top-secret-token",
            }
        },
    }
    state = get_provider_credential_state("real_stub", config)
    dumped = json.dumps(state)
    assert "ultra-secret" not in dumped
    assert "top-secret-token" not in dumped
    assert "api_key" not in dumped
    assert "token" not in dumped


def test_no_network_or_secrets_required_for_provider_foundation():
    config = get_provider_config()
    config_snapshot = copy.deepcopy(config)

    assert "api_key" not in config
    assert "token" not in config

    provider = MockProvider()
    result = provider.render({"shot_id": "shot_scene_001_001", "prompt": {}})

    assert result["status"] == "success"
    assert config == config_snapshot


def test_real_provider_stub_disabled_returns_real_provider_disabled():
    provider = RealProviderStub(get_provider_config())
    result = provider.render({"shot_id": "shot_scene_001_001", "prompt": {}})
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "real_stub",
        "error": "Real provider disabled",
        "error_code": "provider_disabled",
        "meta": {"file_path": None, "url": None},
    }


def test_real_provider_stub_enabled_missing_credentials_returns_missing_credentials():
    provider = RealProviderStub(
        {
            "enabled_providers": ["mock", "real_stub"],
        }
    )
    result = provider.render({"shot_id": "shot_scene_001_001", "prompt": {}})
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "real_stub",
        "error": "Missing credentials",
        "error_code": "missing_credentials",
        "meta": {"file_path": None, "url": None},
    }


def test_real_provider_stub_enabled_with_credentials_returns_execution_not_implemented():
    provider = RealProviderStub(
        {
            "enabled_providers": ["mock", "real_stub"],
            "provider_credentials": {
                "real_stub": {"credential": "***placeholder***"},
            },
        }
    )
    result = provider.render({"shot_id": "shot_scene_001_001", "prompt": {}})
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "real_stub",
        "error": "Execution not implemented",
        "error_code": "not_implemented",
        "meta": {"file_path": None, "url": None},
    }


def test_only_mock_provider_can_return_success_status():
    mock_result = MockProvider().render({"shot_id": "shot_scene_001_001", "prompt": {}})
    real_result = RealProviderStub(
        {
            "enabled_providers": ["mock", "real_stub"],
            "provider_credentials": {
                "real_stub": {"credential": "***placeholder***"},
            },
        }
    ).render({"shot_id": "shot_scene_001_001", "prompt": {}})

    assert mock_result["status"] == "success"
    assert real_result["status"] != "success"


def test_real_provider_stub_no_network_usage(monkeypatch):
    called = {"socket_called": False}

    def _socket_guard(*args, **kwargs):
        called["socket_called"] = True
        raise AssertionError("Network socket should not be used by RealProviderStub")

    monkeypatch.setattr(socket, "socket", _socket_guard)

    provider = RealProviderStub(
        {
            "enabled_providers": ["mock", "real_stub"],
            "provider_credentials": {
                "real_stub": {"credential": "***placeholder***"},
            },
        }
    )
    result = provider.render({"shot_id": "shot_scene_001_001", "prompt": {}})
    assert result["error"] == "Execution not implemented"
    assert called["socket_called"] is False


def test_real_provider_stub_deterministic_outputs():
    provider = RealProviderStub(
        {
            "enabled_providers": ["mock", "real_stub"],
            "provider_credentials": {
                "real_stub": {"credential": "***placeholder***"},
            },
        }
    )
    payload = {"shot_id": "shot_scene_001_001", "prompt": {}}
    first = provider.render(payload)
    second = provider.render(payload)
    assert first == second


def test_execution_layer_success_path_with_mock_provider():
    result = execute_provider_render(
        provider_name="mock",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {}},
        config=get_provider_config(),
    )
    assert result == {
        "render_id": "mock_shot_scene_001_001",
        "status": "success",
        "provider": "mock",
        "error": None,
        "error_code": None,
        "meta": {"file_path": None, "url": None},
    }


def test_execution_layer_invalid_payload_returns_normalized_failure():
    result = execute_provider_render(
        provider_name="mock",
        provider_payload={"shot_id": None, "prompt": {}},
        config=get_provider_config(),
    )
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "mock",
        "error": "Invalid provider payload",
        "error_code": "invalid_payload",
        "meta": {"file_path": None, "url": None},
    }


def test_execution_layer_unknown_provider_returns_normalized_failure():
    result = execute_provider_render(
        provider_name="unknown_provider",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {}},
        config={
            "default_provider": "unknown_provider",
            "enabled_providers": ["unknown_provider"],
        },
    )
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "mock",
        "error": "Unknown provider: unknown_provider",
        "error_code": "unknown_provider",
        "meta": {"file_path": None, "url": None},
    }


def test_mock_provider_still_default_path_through_execution_layer():
    result = execute_provider_render(
        provider_name=None,
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {}},
        config=get_provider_config(),
    )
    assert result == {
        "render_id": "mock_shot_scene_001_001",
        "status": "success",
        "provider": "mock",
        "error": None,
        "error_code": None,
        "meta": {"file_path": None, "url": None},
    }


def test_execution_layer_provider_exception_returns_normalized_failure():
    class ExplodingProvider(RenderProvider):
        name = "exploder"

        def render(self, payload):
            raise RuntimeError("provider boom")

    registry = ProviderRegistry()
    registry.register_provider("exploder", ExplodingProvider())
    result = execute_provider_render(
        provider_name="exploder",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {}},
        config={"provider_registry": registry, "enabled_providers": ["mock", "exploder"]},
    )
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "mock",
        "error": "provider boom",
        "error_code": "provider_exception",
        "meta": {"file_path": None, "url": None},
    }


def test_execution_layer_malformed_provider_result_is_normalized():
    class BadResultProvider(RenderProvider):
        name = "badresult"

        def render(self, payload):
            return {"status": "unknown"}

    registry = ProviderRegistry()
    registry.register_provider("badresult", BadResultProvider())
    result = execute_provider_render(
        provider_name="badresult",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {}},
        config={"provider_registry": registry, "enabled_providers": ["mock", "badresult"]},
    )
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "mock",
        "error": "Malformed provider result",
        "error_code": "malformed_result",
        "meta": {"file_path": None, "url": None},
    }


def test_script_parser_still_builds_bundle_without_crashing():
    parser = ScriptParser()
    script = """
INT. APARTMENT - NIGHT

MAYA
We need a plan.
"""
    bundle = parser.build_script_breakdown_bundle(script)
    assert "execution_result_v2" in bundle
    assert "output_sync" in bundle
    assert "execution_monitor" in bundle


def test_execution_result_regression_guard_mock_success_path_unchanged():
    parser = ScriptParser()
    result = parser.build_execution_result_v2(
        {
            "enabled": True,
            "shot_id": "shot_scene_001_001",
            "prompt": {
                "base_intent": "Opening line",
                "visual_tokens": [],
                "shot_tokens": [],
            },
        },
        {
            "shot_id": "shot_scene_001_001",
            "prompt": {
                "base_intent": "Opening line",
                "visual_tokens": [],
                "shot_tokens": [],
            },
        },
    )
    assert result == {
        "execution_result_v2": {
            "executed": True,
            "render_id": "mock_shot_scene_001_001",
            "status": "success",
        }
    }


def test_script_parser_has_no_provider_import_leakage():
    parser_path = Path(__file__).resolve().parents[1] / "script_parser.py"
    source = parser_path.read_text(encoding="utf-8")

    assert "from .providers.real_provider_adapter import execute_real_image_render" not in source
    assert "from .providers.local_image_provider import execute_local_image_render" not in source
    assert "execute_render(" in source
    assert "app.services.providers" not in source


def test_execution_isolation_outputs_are_deterministic_across_calls():
    payload = {"shot_id": "shot_scene_001_001", "prompt": {}}
    config = get_provider_config()

    first = execute_provider_render("mock", payload, config)
    second = execute_provider_render("mock", payload, config)
    assert first == second

    first_failure = execute_provider_render("missing", payload, config)
    second_failure = execute_provider_render("missing", payload, config)
    assert first_failure == second_failure


def test_render_executor_delegates_to_execution_layer(monkeypatch):
    calls = []

    def _fake_execute_provider_render(provider_name, provider_payload, config):
        calls.append((provider_name, provider_payload, config))
        return {
            "render_id": "mock_shot_scene_001_001",
            "status": "success",
            "provider": "mock",
            "error": None,
            "error_code": None,
            "meta": {"file_path": None, "url": None},
        }

    monkeypatch.setattr(render_executor, "execute_provider_render", _fake_execute_provider_render)

    payload = {"shot_id": "shot_scene_001_001", "prompt": {"base_intent": "intent"}}
    config = {"enabled_providers": ["mock"]}
    result = render_executor.execute_render(payload, provider_name="mock", config=config)

    assert result == {
        "render_id": "mock_shot_scene_001_001",
        "status": "success",
        "provider": "mock",
        "error": None,
        "error_code": None,
        "meta": {"file_path": None, "url": None},
    }
    assert calls == [("mock", payload, config)]


def test_provider_outputs_never_include_credential_material():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "provider_credentials": {
            "real_stub": {
                "credential": "ultra-secret-provider-key",
            }
        },
    }
    result = execute_provider_render(
        provider_name="real_stub",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {}},
        config=config,
    )
    dumped = json.dumps(result)
    assert "ultra-secret-provider-key" not in dumped
    assert "credential" not in dumped
    assert "api_key" not in dumped
    assert "token" not in dumped


def test_no_async_retry_or_batching_tokens_in_provider_execution_path():
    backend_root = Path(__file__).resolve().parents[1]
    execution_layer_source = (backend_root / "providers" / "execution_layer.py").read_text(
        encoding="utf-8"
    )
    render_executor_source = (backend_root / "render_executor.py").read_text(encoding="utf-8")
    real_adapter_source = (backend_root / "providers" / "real_provider_adapter.py").read_text(
        encoding="utf-8"
    )
    local_image_source = (backend_root / "providers" / "local_image_provider.py").read_text(
        encoding="utf-8"
    )

    forbidden_tokens = [
        "async def",
        "await ",
        "asyncio",
        "retry",
        "batch",
        "ThreadPoolExecutor",
    ]

    for token in forbidden_tokens:
        assert token not in execution_layer_source
        assert token not in render_executor_source
        assert token not in real_adapter_source
        assert token not in local_image_source

    config = get_provider_config()
    first_audit = select_provider_with_audit("missing", config)
    second_audit = select_provider_with_audit("missing", config)
    assert first_audit == second_audit

    first_credential = get_provider_credential_state("real_stub", config)
    second_credential = get_provider_credential_state("real_stub", config)
    assert first_credential == second_credential


def test_provider_config_snapshot_default_shape():
    snapshot = build_provider_config_snapshot(get_provider_config())
    assert snapshot == {
        "default_provider": "mock",
        "enabled_providers": ["mock"],
        "quality_priority": "cinematic_quality",
        "real_providers_enabled": False,
    }


def test_provider_config_snapshot_malformed_config_fallback():
    snapshot = build_provider_config_snapshot({"enabled_providers": "bad"})
    assert snapshot == {
        "default_provider": "mock",
        "enabled_providers": ["mock"],
        "quality_priority": "cinematic_quality",
        "real_providers_enabled": False,
    }


def test_provider_config_snapshot_no_secret_leakage():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "quality_priority": "cinematic_quality",
        "provider_credentials": {
            "real_stub": {
                "api_key": "super-secret-value",
            }
        },
    }
    snapshot = build_provider_config_snapshot(config)
    dumped = json.dumps(snapshot)
    assert "provider_credentials" not in dumped
    assert "api_key" not in dumped
    assert "super-secret-value" not in dumped
    assert snapshot["real_providers_enabled"] is True


def test_provider_registry_snapshot_exact_shape():
    assert build_provider_registry_snapshot() == {
        "provider_registry_snapshot": {
            "available_providers": ["mock", "real_stub"],
            "default_provider": "mock",
            "real_providers_present": True,
        }
    }


def test_provider_activation_state_defaults_to_mock_and_stays_locked():
    assert build_provider_activation_state(None) == {
        "provider_activation_state": {
            "active_provider": "mock",
            "real_enabled": False,
            "real_provider_runtime_flag": False,
            "reason": "Real providers disabled by default",
        }
    }
    assert build_provider_activation_state(
        {"default_provider": "real_stub", "enabled_providers": ["mock", "real_stub"]}
    ) == {
        "provider_activation_state": {
            "active_provider": "real_stub",
            "real_enabled": False,
            "real_provider_runtime_flag": False,
            "reason": "Real providers disabled by default",
        }
    }
    assert build_provider_activation_state(
        {
            "default_provider": "real_stub",
            "enabled_providers": ["mock", "real_stub"],
            "real_enabled": True,
            "real_provider_runtime_flag": True,
        }
    ) == {
        "provider_activation_state": {
            "active_provider": "real_stub",
            "real_enabled": True,
            "real_provider_runtime_flag": True,
            "reason": "Real providers enabled by explicit config",
        }
    }


def test_provider_config_validation_handles_missing_and_malformed():
    assert build_provider_config_validation(None) == {
        "provider_config_validation": {
            "valid": True,
            "issues": [],
            "reason": "Provider config missing; defaults applied",
        }
    }
    assert build_provider_config_validation({"enabled_providers": "bad"}) == {
        "provider_config_validation": {
            "valid": False,
            "issues": ["enabled_providers_invalid"],
            "reason": "Provider config malformed",
        }
    }


def test_credential_validation_enablement_intent_contract_and_safety_shapes():
    assert build_credential_validation_summary(
        {"provider": "mock", "credential_present": True}
    ) == {
        "credential_validation_summary": {
            "provider": "mock",
            "valid": True,
            "reason": "Credential available",
        }
    }
    assert build_credential_validation_summary(
        {"provider": "real_stub", "credential_present": False}
    ) == {
        "credential_validation_summary": {
            "provider": "real_stub",
            "valid": False,
            "reason": "Credential missing",
        }
    }

    assert build_provider_enablement_gate({}, {}) == {
        "provider_enablement_gate": {
            "enabled": False,
            "reason": "Real providers disabled by safety policy",
        }
    }
    assert build_provider_enablement_gate(
        {"active_provider": "real_stub", "real_enabled": True},
        {"provider": "real_stub", "valid": True, "reason": "Credential available"},
    ) == {
        "provider_enablement_gate": {
            "enabled": False,
            "reason": "Real providers disabled by safety policy",
        }
    }
    assert build_provider_enablement_gate(
        {
            "active_provider": "real_stub",
            "real_enabled": True,
            "real_provider_runtime_flag": True,
        },
        {"provider": "real_stub", "valid": True, "reason": "Credential available"},
    ) == {
        "provider_enablement_gate": {
            "enabled": True,
            "reason": "Real provider enabled by explicit gate",
        }
    }
    assert build_provider_intent_signal(
        {"requested_provider": "real_stub", "selected_provider": "real_stub"}
    ) == {
        "provider_intent_signal": {
            "requested": "real_stub",
            "intended": "real_stub",
            "allowed": False,
        }
    }
    assert build_provider_intent_signal(
        {"requested_provider": "mock", "selected_provider": "mock"}
    ) == {
        "provider_intent_signal": {
            "requested": "mock",
            "intended": "mock",
            "allowed": True,
        }
    }

    assert build_provider_activation_contract() == {
        "provider_activation_contract": {
            "real_execution_enabled": False,
            "manual_enable_required": True,
            "safe_mode": True,
            "reason": "Provider activation requires explicit unlock",
        }
    }
    assert build_provider_safety_summary({}, {}) == {
        "provider_safety_summary": {
            "safe": True,
            "execution_allowed": False,
            "mode": "locked",
        }
    }
    assert build_provider_safety_summary(
        {"enabled": True, "reason": "Real provider enabled by explicit gate"},
        {},
    ) == {
        "provider_safety_summary": {
            "safe": True,
            "execution_allowed": True,
            "mode": "enabled",
        }
    }


def test_provider_selection_state_default_mock():
    state = build_provider_selection_state(None, get_provider_config())
    assert state == {
        "requested_provider": "mock",
        "selected_provider": "mock",
        "allowed": True,
        "fallback_used": False,
        "reason": "Default provider selected",
    }


def test_provider_selection_state_enabled_provider_selected():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
    }
    state = build_provider_selection_state("real_stub", config)
    assert state == {
        "requested_provider": "real_stub",
        "selected_provider": "real_stub",
        "allowed": True,
        "fallback_used": False,
        "reason": "Requested provider enabled",
    }


def test_provider_selection_state_disabled_unknown_fallback():
    state = build_provider_selection_state("unknown_provider", get_provider_config())
    assert state == {
        "requested_provider": "unknown_provider",
        "selected_provider": "mock",
        "allowed": False,
        "fallback_used": True,
        "reason": "Requested provider disabled",
    }


def test_provider_selection_state_deterministic():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
    }
    first = build_provider_selection_state("real_stub", config)
    second = build_provider_selection_state("real_stub", config)
    assert first == second


def test_selection_request_schema_none_input():
    assert normalize_selection_request(None) == {"requested_provider": None}


def test_selection_request_schema_whitespace_input():
    assert normalize_selection_request("   ") == {"requested_provider": None}


def test_selection_request_schema_uppercase_input():
    assert normalize_selection_request("  REAL_STUB  ") == {"requested_provider": "real_stub"}


def test_selection_request_schema_deterministic_repeated_calls():
    first = normalize_selection_request("  MOCK ")
    second = normalize_selection_request("  MOCK ")
    assert first == second


def test_resolve_provider_selection_default_to_mock():
    state = resolve_provider_selection(None, get_provider_config())
    assert state == {
        "requested_provider": None,
        "selected_provider": "mock",
        "allowed": True,
        "fallback_used": False,
        "reason": "Default provider selected",
    }


def test_resolve_provider_selection_enabled_provider_selected():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
    }
    state = resolve_provider_selection("real_stub", config)
    assert state == {
        "requested_provider": "real_stub",
        "selected_provider": "real_stub",
        "allowed": True,
        "fallback_used": False,
        "reason": "Requested provider enabled",
    }


def test_resolve_provider_selection_disabled_provider_fallback():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock"],
    }
    state = resolve_provider_selection("real_stub", config)
    assert state == {
        "requested_provider": "real_stub",
        "selected_provider": "mock",
        "allowed": False,
        "fallback_used": True,
        "reason": "Requested provider disabled",
    }


def test_resolve_provider_selection_unknown_provider_fallback():
    state = resolve_provider_selection("unknown_provider", get_provider_config())
    assert state == {
        "requested_provider": "unknown_provider",
        "selected_provider": "mock",
        "allowed": False,
        "fallback_used": True,
        "reason": "Requested provider disabled",
    }


def test_resolve_provider_selection_deterministic_outputs():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
    }
    first = resolve_provider_selection("real_stub", config)
    second = resolve_provider_selection("real_stub", config)
    assert first == second


def test_manual_provider_selection_contract_exact_shape():
    contract = build_manual_provider_selection_contract()
    assert contract == {
        "selection_mode": "manual_only",
        "auto_execution": False,
        "execution_on_select": False,
        "reason": "Provider selection does not trigger execution",
    }


def test_manual_provider_selection_contract_no_mutation():
    first = build_manual_provider_selection_contract()
    first["selection_mode"] = "changed"
    second = build_manual_provider_selection_contract()
    assert second == {
        "selection_mode": "manual_only",
        "auto_execution": False,
        "execution_on_select": False,
        "reason": "Provider selection does not trigger execution",
    }


def test_provider_readiness_summary_mock_readiness():
    summary = build_provider_readiness_summary("mock", get_provider_config())
    assert summary == {
        "provider": "mock",
        "enabled": True,
        "credential_present": True,
        "can_execute": False,
        "reason": "Execution not enabled",
    }


def test_provider_readiness_summary_real_stub_disabled_by_default():
    summary = build_provider_readiness_summary("real_stub", get_provider_config())
    assert summary == {
        "provider": "real_stub",
        "enabled": False,
        "credential_present": False,
        "can_execute": False,
        "reason": "Provider disabled by config",
    }


def test_provider_readiness_summary_real_stub_enabled_missing_credentials():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "quality_priority": "cinematic_quality",
    }
    summary = build_provider_readiness_summary("real_stub", config)
    assert summary == {
        "provider": "real_stub",
        "enabled": True,
        "credential_present": False,
        "can_execute": False,
        "reason": "Missing credentials",
    }


def test_provider_readiness_summary_real_stub_enabled_with_credentials():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "quality_priority": "cinematic_quality",
        "provider_credentials": {
            "real_stub": {
                "credential": "***placeholder***",
            }
        },
    }
    summary = build_provider_readiness_summary("real_stub", config)
    assert summary == {
        "provider": "real_stub",
        "enabled": True,
        "credential_present": True,
        "can_execute": False,
        "reason": "Execution not enabled",
    }


def test_provider_readiness_summary_malformed_config_fallback_safe():
    summary = build_provider_readiness_summary("real_stub", {"enabled_providers": "bad-shape"})
    assert summary == {
        "provider": "real_stub",
        "enabled": False,
        "credential_present": False,
        "can_execute": False,
        "reason": "Provider disabled by config",
    }


def test_provider_readiness_summary_deterministic_repeated_calls():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "provider_credentials": {
            "real_stub": {
                "credential": "***placeholder***",
            }
        },
    }
    first = build_provider_readiness_summary("real_stub", config)
    second = build_provider_readiness_summary("real_stub", config)
    assert first == second


def test_provider_readiness_summary_no_credential_leakage_in_output():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "provider_credentials": {
            "real_stub": {
                "api_key": "super-secret-value",
                "token": "ultra-token",
            }
        },
    }
    summary = build_provider_readiness_summary("real_stub", config)
    dumped = json.dumps(summary)
    assert "super-secret-value" not in dumped
    assert "ultra-token" not in dumped
    assert "api_key" not in dumped
    assert "token" not in dumped


def test_failure_model_helpers_are_deterministic():
    first = build_provider_failure("failed", "invalid_payload", "Invalid provider payload", "mock")
    second = build_provider_failure("failed", "invalid_payload", "Invalid provider payload", "mock")
    assert first == second

    normalized = normalize_provider_failure(
        {"provider": "mock", "error_code": "unknown_provider", "reason": "Unknown provider: mock"}
    )
    assert normalized == {
        "render_id": None,
        "status": "failed",
        "provider": "mock",
        "error": "Unknown provider: mock",
        "error_code": "unknown_provider",
        "meta": {"file_path": None, "url": None},
    }


def test_normalize_provider_result_valid_mock_success():
    normalized = normalize_provider_result(
        {
            "render_id": "mock_shot_scene_001_001",
            "status": "success",
            "provider": "mock",
            "error": None,
        },
        "mock",
    )
    assert normalized == {
        "render_id": "mock_shot_scene_001_001",
        "status": "success",
        "provider": "mock",
        "error": None,
        "error_code": None,
        "meta": {"file_path": None, "url": None},
    }


def test_normalize_provider_result_skipped():
    normalized = normalize_provider_result(
        {
            "status": "not_executed",
            "provider": "mock",
        },
        "mock",
    )
    assert normalized == {
        "render_id": None,
        "status": "not_executed",
        "provider": "mock",
        "error": None,
        "error_code": None,
        "meta": {"file_path": None, "url": None},
    }


def test_normalize_provider_result_provider_exception():
    normalized = normalize_provider_result(RuntimeError("provider boom"), "exploder")
    assert normalized == {
        "render_id": None,
        "status": "failed",
        "provider": "mock",
        "error": "provider boom",
        "error_code": "provider_exception",
        "meta": {"file_path": None, "url": None},
    }


def test_normalize_provider_result_malformed_dict_and_none():
    malformed_dict = normalize_provider_result({"status": "unknown"}, "badresult")
    none_result = normalize_provider_result(None, "badresult")
    assert malformed_dict == {
        "render_id": None,
        "status": "failed",
        "provider": "mock",
        "error": "Malformed provider result",
        "error_code": "malformed_result",
        "meta": {"file_path": None, "url": None},
    }
    assert none_result == {
        "render_id": None,
        "status": "failed",
        "provider": "mock",
        "error": "Malformed provider result",
        "error_code": "malformed_result",
        "meta": {"file_path": None, "url": None},
    }


def test_normalize_provider_result_real_stub_success_is_allowed():
    normalized = normalize_provider_result(
        {
            "render_id": "real_shot_scene_001_001",
            "status": "success",
            "provider": "real_stub",
            "error": None,
            "meta": {"file_path": "/tmp/studio_renders/real_shot_scene_001_001.png", "url": None},
        },
        "real_stub",
    )
    assert normalized == {
        "render_id": "real_shot_scene_001_001",
        "status": "success",
        "provider": "real_stub",
        "error": None,
        "error_code": None,
        "meta": {"file_path": "/tmp/studio_renders/real_shot_scene_001_001.png", "url": None},
    }


def test_normalize_provider_result_is_deterministic_and_non_throwing():
    payload = {
        "status": "failed",
        "provider": "mock",
        "error": "Invalid provider payload",
        "error_code": "invalid_payload",
    }
    first = normalize_provider_result(payload, "mock")
    second = normalize_provider_result(payload, "mock")
    assert first == second

    # no-throw guard
    normalize_provider_result(object(), "mock")


def test_normalize_provider_result_always_has_all_required_fields():
    normalized_cases = [
        normalize_provider_result(None, "mock"),
        normalize_provider_result(RuntimeError("x"), "mock"),
        normalize_provider_result({"status": "not_executed", "provider": "mock"}, "mock"),
        normalize_provider_result(
            {"status": "success", "provider": "mock", "render_id": "mock_shot_scene_001_001"},
            "mock",
        ),
    ]
    for normalized in normalized_cases:
        assert set(normalized.keys()) == {
            "render_id",
            "status",
            "provider",
            "error",
            "error_code",
            "meta",
        }


def test_build_provider_selection_audit_deterministic():
    first = build_provider_selection_audit(
        requested_provider="real_stub",
        selected_provider="mock",
        allowed=False,
        reason="Requested provider disabled",
        fallback_used=True,
    )
    second = build_provider_selection_audit(
        requested_provider="real_stub",
        selected_provider="mock",
        allowed=False,
        reason="Requested provider disabled",
        fallback_used=True,
    )
    assert first == second


def test_build_execution_context_does_not_mutate_payload():
    payload = {"shot_id": "shot_scene_001_001", "prompt": {"base_intent": "Opening line"}}
    payload_original = copy.deepcopy(payload)
    config = get_provider_config()
    _ = build_execution_context("mock", payload, config)
    assert payload == payload_original


# -----------------------------
# Phase 160: Provider Control Regression Harness
# -----------------------------


def test_phase160_mock_is_default_provider():
    config = get_provider_config()
    assert config["default_provider"] == "mock"
    assert "mock" in config["enabled_providers"]


def test_phase160_real_provider_disabled_by_default():
    summary = build_provider_readiness_summary("real_stub", None)
    assert summary["enabled"] is False
    assert summary["can_execute"] is False


def test_phase160_manual_selection_contract_blocks_execution():
    contract = build_manual_provider_selection_contract()
    assert contract["selection_mode"] == "manual_only"
    assert contract["auto_execution"] is False
    assert contract["execution_on_select"] is False


def test_phase160_unknown_provider_selection_falls_back_to_mock():
    state = build_provider_selection_state("unknown_provider", get_provider_config())
    assert state["selected_provider"] == "mock"
    assert state["allowed"] is False
    assert state["fallback_used"] is True


def test_phase160_real_stub_with_credentials_still_cannot_execute():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "provider_credentials": {"real_stub": {"credential": "***placeholder***"}},
    }
    summary = build_provider_readiness_summary("real_stub", config)
    assert summary["enabled"] is True
    assert summary["credential_present"] is True
    assert summary["can_execute"] is False
    assert summary["reason"] == "Execution not enabled"


def test_phase160_config_snapshot_remains_secret_safe():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "provider_credentials": {"real_stub": {"api_key": "secret-key-material"}},
    }
    snapshot = build_provider_config_snapshot(config)
    dumped = json.dumps(snapshot)
    assert "provider_credentials" not in dumped
    assert "api_key" not in dumped
    assert "secret-key-material" not in dumped


def test_phase160_unknown_provider_does_not_crash_execution_layer():
    result = execute_provider_render(
        provider_name="unknown_provider",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {}},
        config=get_provider_config(),
    )
    assert result["status"] == "success"
    assert result["provider"] == "mock"


def test_phase160_malformed_provider_result_is_normalized_failure():
    class BadResultProvider(RenderProvider):
        name = "badresult_phase160"

        def render(self, payload):
            return {"status": "bad-status"}

    registry = ProviderRegistry()
    registry.register_provider("badresult_phase160", BadResultProvider())
    result = execute_provider_render(
        provider_name="badresult_phase160",
        provider_payload={"shot_id": "shot_scene_001_001", "prompt": {}},
        config={"provider_registry": registry, "enabled_providers": ["mock", "badresult_phase160"]},
    )
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "mock",
        "error": "Malformed provider result",
        "error_code": "malformed_result",
        "meta": {"file_path": None, "url": None},
    }


def test_phase160_script_parser_has_no_provider_imports():
    parser_path = Path(__file__).resolve().parents[1] / "script_parser.py"
    source = parser_path.read_text(encoding="utf-8")
    assert "from .providers.real_provider_adapter import execute_real_image_render" not in source
    assert "from .providers.local_image_provider import execute_local_image_render" not in source
    assert "execute_render(" in source
    assert "app.services.providers" not in source


def test_phase160_render_executor_delegates_to_execution_layer(monkeypatch):
    calls = []

    def _fake_execute_provider_render(provider_name, provider_payload, config):
        calls.append((provider_name, provider_payload, config))
        return {
            "render_id": "mock_shot_scene_001_001",
            "status": "success",
            "provider": "mock",
            "error": None,
        }

    monkeypatch.setattr(render_executor, "execute_provider_render", _fake_execute_provider_render)
    payload = {"shot_id": "shot_scene_001_001", "prompt": {"base_intent": "intent"}}
    config = {"enabled_providers": ["mock"]}
    result = render_executor.execute_render(payload, provider_name="mock", config=config)

    assert result["status"] == "success"
    assert calls == [("mock", payload, config)]


def test_phase160_no_async_retry_batching_tokens():
    backend_root = Path(__file__).resolve().parents[1]
    execution_layer_source = (backend_root / "providers" / "execution_layer.py").read_text(
        encoding="utf-8"
    )
    render_executor_source = (backend_root / "render_executor.py").read_text(encoding="utf-8")
    real_adapter_source = (backend_root / "providers" / "real_provider_adapter.py").read_text(
        encoding="utf-8"
    )
    local_image_source = (backend_root / "providers" / "local_image_provider.py").read_text(
        encoding="utf-8"
    )
    forbidden_tokens = ["async def", "await ", "asyncio", "retry", "batch", "ThreadPoolExecutor"]
    for token in forbidden_tokens:
        assert token not in execution_layer_source
        assert token not in render_executor_source
        assert token not in real_adapter_source
        assert token not in local_image_source


def test_phase160_provider_control_deterministic_repeated_calls():
    config = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "provider_credentials": {"real_stub": {"credential": "***placeholder***"}},
    }
    state_first = build_provider_selection_state("real_stub", config)
    state_second = build_provider_selection_state("real_stub", config)
    summary_first = build_provider_readiness_summary("real_stub", config)
    summary_second = build_provider_readiness_summary("real_stub", config)
    contract_first = build_manual_provider_selection_contract()
    contract_second = build_manual_provider_selection_contract()

    assert state_first == state_second
    assert summary_first == summary_second
    assert contract_first == contract_second


def test_phase161_provider_control_fields_present_in_bundle_and_fallbacks():
    parser = ScriptParser()
    valid_bundle = parser.build_script_breakdown_bundle(
        """
INT. APARTMENT - NIGHT

MAYA
We need a plan.
"""
    )
    empty_bundle = parser.build_script_breakdown_bundle("")
    invalid_bundle = parser.build_script_breakdown_bundle(None)

    for bundle in (valid_bundle, empty_bundle, invalid_bundle):
        assert bundle["provider_config_snapshot"] == {
            "default_provider": "mock",
            "enabled_providers": ["mock"],
            "quality_priority": "cinematic_quality",
            "real_providers_enabled": False,
        }
        assert bundle["provider_credential_state"] == {
            "provider": "mock",
            "enabled": True,
            "credential_present": True,
            "credential_source": "none",
            "reason": "Mock provider does not require credentials",
        }
        assert bundle["provider_selection_state"] == {
            "requested_provider": None,
            "selected_provider": "mock",
            "allowed": True,
            "fallback_used": False,
            "reason": "Default provider selected",
        }
        assert bundle["provider_readiness_summary"] == {
            "provider": "mock",
            "enabled": True,
            "credential_present": True,
            "can_execute": False,
            "reason": "Execution not enabled",
        }
        assert bundle["provider_capability"] == {
            "provider": "mock",
            "enabled": True,
            "network_required": False,
            "supports_render": True,
            "supports_streaming": False,
            "supports_sync": True,
            "supports_multi_shot": False,
            "requires_credentials": False,
        }
        assert bundle["provider_control_contract"] == {
            "selection_mode": "manual_only",
            "auto_execution": False,
            "execution_on_select": False,
            "reason": "Provider selection does not trigger execution",
        }
        assert bundle["provider_safety_contract"] == {
            "real_provider_execution_enabled": False,
            "reason": "Real provider execution is disabled by safety boundary",
        }


def test_phase161_provider_control_bundle_secret_safe():
    parser = ScriptParser()
    bundle = parser.build_script_breakdown_bundle(
        """
INT. APARTMENT - NIGHT

MAYA
We need a plan.
"""
    )
    dumped = json.dumps(
        {
            "provider_config_snapshot": bundle["provider_config_snapshot"],
            "provider_credential_state": bundle["provider_credential_state"],
            "provider_selection_state": bundle["provider_selection_state"],
            "provider_readiness_summary": bundle["provider_readiness_summary"],
            "provider_capability": bundle["provider_capability"],
            "provider_control_contract": bundle["provider_control_contract"],
            "provider_safety_contract": bundle["provider_safety_contract"],
        }
    )
    assert "provider_credentials" not in dumped
    assert "api_key" not in dumped
    assert "token" not in dumped
    assert "secret" not in dumped


def test_provider_safety_contract_exact_shape_and_no_mutation():
    first = build_provider_safety_contract()
    second = build_provider_safety_contract()
    assert first == {
        "real_provider_execution_enabled": False,
        "reason": "Real provider execution is disabled by safety boundary",
    }
    assert second == first

    first["real_provider_execution_enabled"] = True
    assert build_provider_safety_contract() == {
        "real_provider_execution_enabled": False,
        "reason": "Real provider execution is disabled by safety boundary",
    }


def test_phase199_provider_execution_path_boundaries():
    """Phase 199: provider execution path remains isolated and non-async/non-retry/non-batch."""
    parser_path = Path(__file__).resolve().parents[1] / "script_parser.py"
    parser_source = parser_path.read_text(encoding="utf-8")
    assert "from .providers.real_provider_adapter import execute_real_image_render" not in parser_source
    assert "from .providers.local_image_provider import execute_local_image_render" not in parser_source
    assert "execute_render(" in parser_source
    assert "app.services.providers" not in parser_source

    backend_root = Path(__file__).resolve().parents[1]
    execution_layer_source = (backend_root / "providers" / "execution_layer.py").read_text(
        encoding="utf-8"
    )
    render_executor_source = (backend_root / "render_executor.py").read_text(encoding="utf-8")
    real_adapter_source = (backend_root / "providers" / "real_provider_adapter.py").read_text(
        encoding="utf-8"
    )
    local_image_source = (backend_root / "providers" / "local_image_provider.py").read_text(
        encoding="utf-8"
    )
    forbidden_tokens = ["async def", "await ", "asyncio", "retry", "batch", "ThreadPoolExecutor"]
    for token in forbidden_tokens:
        assert token not in execution_layer_source
        assert token not in render_executor_source
        assert token not in real_adapter_source
        assert token not in local_image_source


def test_phase200_provider_execution_never_triggers(monkeypatch):
    """Phase 200: provider execution remains normalized, deterministic, and non-executing."""
    original_normalize = provider_execution_layer.normalize_provider_result
    normalize_calls = []

    def _tracking_normalize(input_result, provider_name):
        normalize_calls.append(provider_name)
        return original_normalize(input_result, provider_name)

    monkeypatch.setattr(provider_execution_layer, "normalize_provider_result", _tracking_normalize)

    config_mock = {
        "default_provider": "mock",
        "enabled_providers": ["mock"],
        "quality_priority": "cinematic_quality",
    }
    payload = {
        "shot_id": "shot_scene_001_001",
        "prompt": {"base_intent": "Opening line", "visual_tokens": [], "shot_tokens": []},
    }

    mock_result = execute_provider_render("mock", payload, config_mock)
    assert mock_result["status"] == "success"
    assert mock_result["provider"] == "mock"

    # Non-mock providers never reach real execution success; they normalize to safe failures.
    config_with_stub = {
        "default_provider": "mock",
        "enabled_providers": ["mock", "real_stub"],
        "quality_priority": "cinematic_quality",
        "provider_credentials": {"real_stub": {"credential": "***placeholder***"}},
    }
    real_stub_result = execute_provider_render("real_stub", payload, config_with_stub)
    assert real_stub_result["status"] == "failed"
    assert real_stub_result["provider"] == "real_stub"
    assert real_stub_result["render_id"] is None

    unknown_result = execute_provider_render("unknown_provider", payload, config_mock)
    assert unknown_result["status"] in {"success", "failed", "not_executed"}
    assert unknown_result["provider"] == "mock"

    # Every execution result is normalized through normalize_provider_result.
    assert len(normalize_calls) >= 3

    backend_root = Path(__file__).resolve().parents[1]
    execution_layer_source = (backend_root / "providers" / "execution_layer.py").read_text(
        encoding="utf-8"
    )
    render_executor_source = (backend_root / "render_executor.py").read_text(encoding="utf-8")
    forbidden_tokens = ["async def", "await ", "asyncio", "retry", "batch", "ThreadPoolExecutor"]
    for token in forbidden_tokens:
        assert token not in execution_layer_source
        assert token not in render_executor_source


def test_real_provider_adapter_deterministic_success_and_failure_shapes():
    success = execute_real_image_render({"base_intent": "Opening line"}, "shot_scene_001_001")
    assert success == {
        "render_id": "real_shot_scene_001_001",
        "status": "success",
        "provider": "real_stub",
        "error": None,
        "error_code": None,
        "meta": {
            "file_path": "/tmp/studio_renders/real_shot_scene_001_001.png",
            "url": None,
        },
    }

    failed = execute_real_image_render(None, "shot_scene_001_001")
    assert failed == {
        "render_id": "real_shot_scene_001_001",
        "status": "failed",
        "provider": "real_stub",
        "error": "Invalid prompt payload",
        "error_code": "invalid_prompt_payload",
        "meta": {"file_path": None, "url": None},
    }


def test_execution_layer_real_provider_stays_blocked_without_explicit_real_enable():
    payload = {"shot_id": "shot_scene_001_001", "prompt": {"base_intent": "Opening line"}}
    config_with_credentials_but_locked = {
        "default_provider": "real_stub",
        "enabled_providers": ["mock", "real_stub"],
        "provider_credentials": {"real_stub": {"credential": "***placeholder***"}},
    }
    result = execute_provider_render("real_stub", payload, config_with_credentials_but_locked)
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "real_stub",
        "error": "Real provider execution locked",
        "error_code": "real_provider_locked",
        "meta": {"file_path": None, "url": None},
    }


def test_execution_layer_real_provider_executes_when_explicitly_enabled_and_credentialed():
    payload = {"shot_id": "shot_scene_001_001", "prompt": {"base_intent": "Opening line"}}
    config_enabled = {
        "default_provider": "real_stub",
        "enabled_providers": ["mock", "real_stub"],
        "real_enabled": True,
        "real_provider_runtime_flag": True,
        "provider_credentials": {"real_stub": {"credential": "***placeholder***"}},
    }
    first = execute_provider_render("real_stub", payload, config_enabled)
    second = execute_provider_render("real_stub", payload, config_enabled)

    expected = {
        "render_id": "real_shot_scene_001_001",
        "status": "success",
        "provider": "real_stub",
        "error": None,
        "error_code": None,
        "meta": {"file_path": "/tmp/studio_renders/real_shot_scene_001_001.png", "url": None},
    }
    assert first == expected
    assert second == expected


def test_local_image_provider_creates_deterministic_artifact_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = execute_local_image_render({"base_intent": "Opening line"}, "shot_scene_001_001")
    assert result == {
        "render_id": "local_shot_scene_001_001",
        "status": "success",
        "provider": "local_image",
        "error": None,
        "error_code": None,
        "meta": {
            "file_path": "output/renders/local_shot_scene_001_001.txt",
            "url": None,
            "artifact_type": "text_preview",
        },
    }
    artifact_path = tmp_path / "output" / "renders" / "local_shot_scene_001_001.txt"
    assert artifact_path.exists()
    assert artifact_path.read_text(encoding="utf-8") == "Local render preview for shot_scene_001_001\n"


def test_local_image_provider_missing_shot_id_fails_with_normalized_shape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = execute_local_image_render({"base_intent": "Opening line"}, None)
    assert result == {
        "render_id": None,
        "status": "failed",
        "provider": "local_image",
        "error": "Missing shot_id",
        "error_code": "missing_shot_id",
        "meta": {
            "file_path": None,
            "url": None,
            "artifact_type": "text_preview",
        },
    }

def test_provider_result_normalization_hardening_phase341_345():
    """
    Phase 341-345: Verify all provider results are normalized with meta guarantees.
    """
    # 1. Successful normalization
    raw_success = {
        "render_id": "test_123",
        "status": "success",
        "provider": "mock",
        "meta": {"other": "data"}
    }
    normalized = normalize_provider_result(raw_success, "mock")
    assert normalized["status"] == "success"
    assert normalized["meta"]["file_path"] is None
    assert normalized["meta"]["url"] is None
    assert normalized["meta"]["other"] == "data"

    # 2. Failure normalization
    raw_failure = {
        "status": "failed",
        "error": "Generic error",
        "error_code": "generic_failure"
    }
    normalized_fail = normalize_provider_result(raw_failure, "local_image")
    assert normalized_fail["status"] == "failed"
    assert normalized_fail["provider"] == "local_image"
    assert normalized_fail["meta"] == {"file_path": None, "url": None}

    # 3. Exception normalization
    normalized_exc = normalize_provider_result(Exception("Crash"), "real_stub")
    assert normalized_exc["status"] == "failed"
    assert normalized_exc["error"] == "Crash"
    assert normalized_exc["error_code"] == "provider_exception"
    assert normalized_exc["meta"] == {"file_path": None, "url": None}

    # 4. Standardized provider names
    assert normalize_provider_result({}, "  MOCK  ")["provider"] == "mock"
    assert normalize_provider_result({}, "LOCAL_IMAGE")["provider"] == "local_image"
    assert normalize_provider_result({}, "real_stub")["provider"] == "real_stub"
    assert normalize_provider_result({}, "unknown")["provider"] == "mock"
