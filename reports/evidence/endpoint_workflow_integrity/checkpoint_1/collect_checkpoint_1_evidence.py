from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[4]
BACKEND = ROOT / "studio-backend"
FRONTEND = ROOT / "studio-app"
OUT = Path(__file__).resolve().parent

FEATURE_PATTERNS = {
    "storyboard": r"\bstory\s*board\b|storyboard",
    "storyboard_blueprint": r"storyboard[_\-\s]?blueprint|blueprint",
    "storyboard_wall": r"storyboard[_\-\s]?wall",
    "previs": r"\bprevis\b|pre-?vis|rough\s+previs",
    "precise": r"\bprecise\b",
    "theatre": r"\btheatre\b",
    "theater": r"\btheater\b",
    "screening_room": r"screening[_\-\s]?room|screening",
    "production_board": r"production[_\-\s]?board",
    "scene_production": r"scene[_\-\s]?production",
    "rendering": r"\brender(ing|s|ed)?\b|render[_\-\s]?job",
    "revisions": r"\brevision(s)?\b|revise|retry",
    "editorial": r"\beditorial\b|editing",
    "film_cut": r"film[_\-\s]?cut|\bcut\b",
    "timeline": r"\btimeline\b",
    "project_state": r"project[_\-\s]?state|studio[_\-\s]?state",
    "memory": r"\bmemory\b|semantic[_\-\s]?memory",
    "continuity": r"\bcontinuity\b",
}


def text_files(base: Path, suffixes: tuple[str, ...]) -> list[Path]:
    skip = {"node_modules", ".venv", "__pycache__", ".pytest_cache", "dist", "build"}
    files: list[Path] = []
    for path in base.rglob("*"):
        if any(part in skip for part in path.parts):
            continue
        if path.is_file() and path.suffix in suffixes:
            files.append(path)
    return sorted(files)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def extract_router_prefixes() -> dict[str, Any]:
    routers: dict[str, Any] = {}
    for file in text_files(BACKEND / "app" / "routes", (".py",)):
        try:
            tree = ast.parse(file.read_text())
        except SyntaxError as exc:
            routers[rel(file)] = {"parse_error": str(exc)}
            continue
        prefixes: list[str | None] = []
        route_defs: list[dict[str, Any]] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name) and fn.id == "APIRouter":
                    prefix = None
                    for kw in node.keywords:
                        if kw.arg == "prefix" and isinstance(kw.value, ast.Constant):
                            prefix = kw.value.value
                    prefixes.append(prefix)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if not isinstance(dec, ast.Call):
                        continue
                    func = dec.func
                    if isinstance(func, ast.Attribute) and func.attr in {
                        "get",
                        "post",
                        "put",
                        "patch",
                        "delete",
                    }:
                        route_defs.append(
                            {
                                "handler": node.name,
                                "method": func.attr.upper(),
                                "path": dec.args[0].value
                                if dec.args and isinstance(dec.args[0], ast.Constant)
                                else None,
                                "request_model_candidates": [
                                    arg.annotation.id
                                    for arg in node.args.args
                                    if isinstance(arg.annotation, ast.Name)
                                ],
                                "response_model": next(
                                    (
                                        kw.value.id
                                        for kw in dec.keywords
                                        if kw.arg == "response_model" and isinstance(kw.value, ast.Name)
                                    ),
                                    None,
                                ),
                            }
                        )
        routers[rel(file)] = {"router_prefixes": prefixes, "route_defs": route_defs}
    return routers


def extract_runtime_routes() -> list[dict[str, Any]]:
    sys.path.insert(0, str(BACKEND))
    os.environ.setdefault("ENVIRONMENT", "test")
    import main  # type: ignore

    routes: list[dict[str, Any]] = []
    openapi = main.app.openapi()
    for route in main.app.routes:
        methods = sorted(getattr(route, "methods", []) or [])
        endpoint = getattr(route, "endpoint", None)
        routes.append(
            {
                "path": getattr(route, "path", None),
                "name": getattr(route, "name", None),
                "methods": methods,
                "endpoint": getattr(endpoint, "__name__", None),
                "include_in_schema": getattr(route, "include_in_schema", None),
                "route_class": route.__class__.__name__,
            }
        )
    schema_paths = []
    for path, methods in sorted(openapi.get("paths", {}).items()):
        for method, spec in sorted(methods.items()):
            schema_paths.append(
                {
                    "method": method.upper(),
                    "path": path,
                    "operation_id": spec.get("operationId"),
                    "summary": spec.get("summary"),
                    "request_body": bool(spec.get("requestBody")),
                    "parameters": spec.get("parameters", []),
                    "responses": sorted(spec.get("responses", {}).keys()),
                }
            )
    return [{"fastapi_routes": routes, "openapi_paths": schema_paths}]


def scan_features() -> dict[str, list[dict[str, Any]]]:
    files = text_files(BACKEND / "app", (".py",)) + text_files(FRONTEND / "src", (".ts", ".tsx"))
    result: dict[str, list[dict[str, Any]]] = {key: [] for key in FEATURE_PATTERNS}
    compiled = {k: re.compile(v, re.IGNORECASE) for k, v in FEATURE_PATTERNS.items()}
    for file in files:
        try:
            lines = file.read_text(errors="ignore").splitlines()
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(lines, start=1):
            for key, pattern in compiled.items():
                if pattern.search(line):
                    result[key].append({"file": rel(file), "line": lineno, "text": line.strip()[:240]})
    return result


def scan_frontend_api_calls() -> list[dict[str, Any]]:
    files = text_files(FRONTEND / "src", (".ts", ".tsx"))
    calls: list[dict[str, Any]] = []
    pattern = re.compile(r"(fetch|axios\.[a-z]+)\(([^)\n]+)")
    path_pattern = re.compile(r"['\"`]((?:/api|/projects|/outputs|/previs-assets|/health)[^'\"`]*)['\"`]")
    for file in files:
        for lineno, line in enumerate(file.read_text(errors="ignore").splitlines(), start=1):
            if "fetch(" not in line and "axios." not in line and "/api/" not in line:
                continue
            paths = path_pattern.findall(line)
            if pattern.search(line) or paths:
                calls.append({"file": rel(file), "line": lineno, "paths": paths, "text": line.strip()[:260]})
    return calls


def scan_models() -> dict[str, list[str]]:
    models = {}
    for file in text_files(BACKEND / "app" / "models", (".py",)):
        names: list[str] = []
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                names.append(node.name)
        models[rel(file)] = names
    return models


def write_json(name: str, data: Any) -> None:
    (OUT / name).write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def main() -> None:
    write_json("source_route_inventory.json", extract_router_prefixes())
    runtime = extract_runtime_routes()[0]
    write_json("runtime_route_inventory.json", runtime["fastapi_routes"])
    write_json("runtime_openapi_inventory.json", runtime["openapi_paths"])
    write_json("feature_reference_scan.json", scan_features())
    write_json("frontend_api_call_scan.json", scan_frontend_api_calls())
    write_json("backend_model_inventory.json", scan_models())


if __name__ == "__main__":
    main()
