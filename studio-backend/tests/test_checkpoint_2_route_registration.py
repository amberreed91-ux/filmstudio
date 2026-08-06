from __future__ import annotations

from collections import Counter
import re
import warnings


def _effective_routes(app):
    for route in app.router.routes:
        effective_candidates = getattr(route, "effective_candidates", None)
        if callable(effective_candidates):
            yield from effective_candidates()
        else:
            yield route


def _method_path_counts(app):
    counts: Counter[tuple[str, tuple[str, ...]]] = Counter()
    handlers: dict[tuple[str, tuple[str, ...]], list[str]] = {}
    for route in _effective_routes(app):
        path = getattr(route, "path", None)
        methods = tuple(sorted(getattr(route, "methods", []) or []))
        endpoint = getattr(route, "endpoint", None)
        if not path or not methods:
            continue
        key = (path, methods)
        counts[key] += 1
        handlers.setdefault(key, []).append(
            f"{getattr(endpoint, '__module__', '')}.{getattr(endpoint, '__name__', '')}"
        )
    return counts, handlers


def _operation_rows(app):
    for index, route in enumerate(_effective_routes(app)):
        path = getattr(route, "path", None)
        endpoint = getattr(route, "endpoint", None)
        if not path:
            continue
        for method in sorted(getattr(route, "methods", []) or []):
            yield {
                "index": index,
                "method": method,
                "path": path,
                "include_in_schema": bool(getattr(route, "include_in_schema", False)),
                "endpoint": (
                    f"{getattr(endpoint, '__module__', '')}."
                    f"{getattr(endpoint, '__name__', '')}"
                ),
            }


def _normalized_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def _path_parts(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def _is_parameter(part: str) -> bool:
    return part.startswith("{") and part.endswith("}")


def _paths_overlap(left: str, right: str) -> bool:
    left_parts = _path_parts(left)
    right_parts = _path_parts(right)
    if len(left_parts) != len(right_parts):
        return False
    return all(
        left_part == right_part
        or _is_parameter(left_part)
        or _is_parameter(right_part)
        for left_part, right_part in zip(left_parts, right_parts)
    )


def test_checkpoint_2_priority_routes_are_mounted_once():
    from main import app

    counts, handlers = _method_path_counts(app)
    required_once = {
        ("/api/f51/studio/projects/{project_id}/reference-assets", ("GET",)),
        ("/api/f51/studio/projects/{project_id}/reference-assets", ("POST",)),
        (
            "/api/f51/studio/projects/{project_id}/shots/{shot_id}/propose-reference",
            ("POST",),
        ),
        (
            "/api/f51/studio/projects/{project_id}/co-director/proactive-check",
            ("POST",),
        ),
        ("/api/f51/studio/projects/{project_id}/co-director/chat", ("POST",)),
        ("/api/f51/studio/debate/trigger", ("POST",)),
        ("/api/f51/studio/debate/action", ("POST",)),
        ("/api/f51/studio/debate/{project_id}", ("GET",)),
        ("/api/f51/studio/video-assets/{asset_id}/extract-keyframes", ("POST",)),
        ("/api/f51/studio/video-assets/{asset_id}/keyframes", ("GET",)),
        ("/api/f51/studio/projects/{project_id}/keyframes", ("GET",)),
        ("/api/f51/studio/video-keyframes/{keyframe_id}", ("GET",)),
        ("/api/f51/studio/video-keyframes/{keyframe_id}/analyze", ("POST",)),
        ("/api/f51/studio/video-assets/{asset_id}/analyze-keyframes", ("POST",)),
        ("/api/f51/studio/video-assets/{asset_id}/frame-analyses", ("GET",)),
        ("/api/f51/studio/projects/{project_id}/frame-analyses", ("GET",)),
    }

    for key in required_once:
        assert counts[key] == 1, f"{key} registered {counts[key]} times via {handlers.get(key, [])}"


def test_checkpoint_2_openapi_has_reference_assets_without_duplicate_warnings():
    from main import app

    app.openapi_schema = None
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        schema = app.openapi()

    warning_text = "\n".join(str(item.message) for item in captured)
    assert "Duplicate Operation ID" not in warning_text
    assert "/api/f51/studio/projects/{project_id}/reference-assets" in schema["paths"]
    assert (
        "/api/f51/studio/projects/{project_id}/shots/{shot_id}/propose-reference"
        in schema["paths"]
    )


def test_checkpoint_2_every_http_operation_is_registered_once():
    from main import app

    registrations: dict[tuple[str, str], list[str]] = {}
    for row in _operation_rows(app):
        key = (row["method"], _normalized_path(row["path"]))
        registrations.setdefault(key, []).append(row["endpoint"])

    duplicates = {
        key: endpoints
        for key, endpoints in registrations.items()
        if len(endpoints) != 1
    }
    assert duplicates == {}


def test_checkpoint_2_static_routes_are_not_shadowed_by_dynamic_routes():
    from main import app

    rows = list(_operation_rows(app))
    shadowed: list[dict[str, str | int]] = []
    for earlier_index, earlier in enumerate(rows):
        for later in rows[earlier_index + 1 :]:
            if earlier["method"] != later["method"]:
                continue
            if earlier["path"] == later["path"]:
                continue
            if not _paths_overlap(earlier["path"], later["path"]):
                continue
            earlier_parts = _path_parts(earlier["path"])
            later_parts = _path_parts(later["path"])
            if any(
                _is_parameter(earlier_part) and not _is_parameter(later_part)
                for earlier_part, later_part in zip(earlier_parts, later_parts)
            ):
                shadowed.append(
                    {
                        "method": earlier["method"],
                        "earlier_path": earlier["path"],
                        "earlier_endpoint": earlier["endpoint"],
                        "later_path": later["path"],
                        "later_endpoint": later["endpoint"],
                    }
                )

    assert shadowed == []


def test_checkpoint_2_runtime_operations_match_openapi():
    from main import app

    runtime_operations = {
        (row["method"], row["path"])
        for row in _operation_rows(app)
        if row["include_in_schema"] and row["method"] not in {"HEAD", "OPTIONS"}
    }
    schema = app.openapi()
    openapi_operations = {
        (method.upper(), path)
        for path, path_item in schema["paths"].items()
        for method in path_item
        if method.upper() in {"GET", "POST", "PUT", "PATCH", "DELETE"}
    }

    assert runtime_operations == openapi_operations


def test_checkpoint_2_final_export_static_routes_precede_artifact_route():
    from main import app

    rows = list(_operation_rows(app))
    get_paths = [row["path"] for row in rows if row["method"] == "GET"]
    status_path = "/api/f51/studio/projects/{project_id}/export/status"
    download_path = "/api/f51/studio/projects/{project_id}/export/download"
    artifact_path = "/api/f51/studio/projects/{project_id}/export/{artifact_type}"

    assert get_paths.index(status_path) < get_paths.index(artifact_path)
    assert get_paths.index(download_path) < get_paths.index(artifact_path)
