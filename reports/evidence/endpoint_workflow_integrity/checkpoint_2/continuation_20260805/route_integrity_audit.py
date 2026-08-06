from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / "studio-backend"))
from main import app


HTTP_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
PRIORITY_PATTERNS = {
    "storyboard": ("storyboard",),
    "previs": ("previs",),
    "screening_review": ("screening", "short-film-review", "review-shot"),
    "production": ("production-board", "production-queue", "scene-production"),
    "rendering": ("/render", "/stitch"),
    "revisions": ("revision", "retry-render"),
    "editorial": ("editorial",),
    "film_cut_timeline": ("film-cut", "timeline"),
    "project_state": ("/projects/",),
    "memory": ("memory",),
    "continuity": ("continuity",),
}


def effective_routes():
    for route in app.router.routes:
        candidates = getattr(route, "effective_candidates", None)
        if callable(candidates):
            yield from candidates()
        else:
            yield route


def normalize_path(path: str) -> str:
    return re.sub(r"\{[^}]+\}", "{}", path)


def path_parts(path: str) -> list[str]:
    return [part for part in path.split("/") if part]


def is_parameter(part: str) -> bool:
    return part.startswith("{") and part.endswith("}")


def paths_overlap(left: str, right: str) -> bool:
    left_parts = path_parts(left)
    right_parts = path_parts(right)
    return len(left_parts) == len(right_parts) and all(
        left_part == right_part
        or is_parameter(left_part)
        or is_parameter(right_part)
        for left_part, right_part in zip(left_parts, right_parts)
    )


rows: list[dict[str, object]] = []
for index, route in enumerate(effective_routes()):
    path = getattr(route, "path", None)
    endpoint = getattr(route, "endpoint", None)
    if not path:
        continue
    for method in sorted(getattr(route, "methods", []) or []):
        if method not in HTTP_METHODS:
            continue
        rows.append(
            {
                "index": index,
                "method": method,
                "path": path,
                "include_in_schema": bool(getattr(route, "include_in_schema", False)),
                "endpoint": (
                    f"{getattr(endpoint, '__module__', '')}."
                    f"{getattr(endpoint, '__name__', '')}"
                ),
            }
        )

counts = Counter((row["method"], normalize_path(str(row["path"]))) for row in rows)
duplicates = {key: count for key, count in counts.items() if count > 1}

shadowed: list[tuple[dict[str, object], dict[str, object]]] = []
for earlier_index, earlier in enumerate(rows):
    for later in rows[earlier_index + 1 :]:
        if earlier["method"] != later["method"]:
            continue
        if earlier["path"] == later["path"]:
            continue
        if not paths_overlap(str(earlier["path"]), str(later["path"])):
            continue
        if any(
            is_parameter(earlier_part) and not is_parameter(later_part)
            for earlier_part, later_part in zip(
                path_parts(str(earlier["path"])),
                path_parts(str(later["path"])),
            )
        ):
            shadowed.append((earlier, later))

schema = app.openapi()
openapi_operations = {
    (method.upper(), path)
    for path, path_item in schema["paths"].items()
    for method in path_item
    if method.upper() in HTTP_METHODS
}
runtime_schema_operations = {
    (str(row["method"]), str(row["path"]))
    for row in rows
    if row["include_in_schema"]
}
forbidden_prefixes = sorted(
    {
        str(row["path"])
        for row in rows
        if str(row["path"]).startswith("/f51/studio")
        or "/api/api/" in str(row["path"])
    }
)

print(f"effective_http_operations={len(rows)}")
print(f"openapi_operations={len(openapi_operations)}")
print(f"normalized_duplicate_operations={len(duplicates)}")
print(f"static_routes_shadowed={len(shadowed)}")
print(f"runtime_openapi_match={runtime_schema_operations == openapi_operations}")
print(f"forbidden_prefixes={len(forbidden_prefixes)}")
for name, patterns in PRIORITY_PATTERNS.items():
    selected = [
        row for row in rows if any(pattern in str(row["path"]).lower() for pattern in patterns)
    ]
    modules = sorted({str(row["endpoint"]).rsplit(".", 1)[0] for row in selected})
    print(f"{name}: operations={len(selected)} modules={len(modules)}")
print(f"precise_routes={sum('precise' in str(row['path']).lower() for row in rows)}")
print(f"theatre_routes={sum('theatre' in str(row['path']).lower() for row in rows)}")
print(f"theater_routes={sum('theater' in str(row['path']).lower() for row in rows)}")

if duplicates:
    print(f"duplicates={duplicates}")
if shadowed:
    for earlier, later in shadowed:
        print(
            "shadow="
            f"{earlier['method']} {earlier['path']} ({earlier['endpoint']}) -> "
            f"{later['path']} ({later['endpoint']})"
        )
if forbidden_prefixes:
    print(f"forbidden_prefix_paths={forbidden_prefixes}")

passed = not duplicates and not shadowed and not forbidden_prefixes
passed = passed and runtime_schema_operations == openapi_operations
print(f"status={'PASS' if passed else 'FAIL'}")
raise SystemExit(0 if passed else 1)
