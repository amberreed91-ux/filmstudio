#!/usr/bin/env python3
from __future__ import annotations

import json

from app.services.demo_seed_service import demo_seed_service


def main() -> int:
    result = demo_seed_service.seed_demo_project(project_id="demo_studio_cinematic_001")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

