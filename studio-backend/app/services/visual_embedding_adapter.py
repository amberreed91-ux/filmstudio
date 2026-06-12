from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class VisualEmbeddingResult:
    vector: List[float]
    dimension: int
    provider: str
    model: str
    status: str
    metadata: Dict[str, object]


class VisualEmbeddingAdapter:
    def embed_image(self, image_path: str, context: Optional[Dict[str, object]] = None) -> VisualEmbeddingResult:
        raise NotImplementedError


class UnavailableVisualEmbeddingAdapter(VisualEmbeddingAdapter):
    def embed_image(self, image_path: str, context: Optional[Dict[str, object]] = None) -> VisualEmbeddingResult:
        return VisualEmbeddingResult(
            vector=[],
            dimension=0,
            provider="unavailable",
            model="unconfigured",
            status="unavailable",
            metadata={"message": "visual embedding provider not configured"},
        )


class MockLocalVisualEmbeddingAdapter(VisualEmbeddingAdapter):
    """Deterministic local embedding adapter for safe QA/testing."""

    def __init__(self, dimension: int = 64):
        self._dimension = max(8, dimension)

    def embed_image(self, image_path: str, context: Optional[Dict[str, object]] = None) -> VisualEmbeddingResult:
        path = Path(image_path)
        if not path.exists() or not path.is_file():
            return VisualEmbeddingResult(
                vector=[],
                dimension=0,
                provider="mock_local",
                model="mock-visual-embedding-v1",
                status="unavailable",
                metadata={"message": "image file not accessible", "path": image_path},
            )
        data = path.read_bytes()
        digest = hashlib.sha256(data).digest()
        vector: List[float] = []
        while len(vector) < self._dimension:
            for byte in digest:
                vector.append((byte / 255.0) * 2.0 - 1.0)
                if len(vector) >= self._dimension:
                    break
            digest = hashlib.sha256(digest).digest()

        norm = sum(v * v for v in vector) ** 0.5 or 1.0
        vector = [round(v / norm, 8) for v in vector]
        return VisualEmbeddingResult(
            vector=vector,
            dimension=len(vector),
            provider="mock_local",
            model="mock-visual-embedding-v1",
            status="complete",
            metadata={"advisory_only": True, "external_call": False, "context": context or {}},
        )


def build_visual_embedding_adapter() -> VisualEmbeddingAdapter:
    provider = (os.getenv("VISUAL_EMBEDDING_PROVIDER") or "").strip().lower()
    if provider in {"mock", "mock_local", "local"}:
        return MockLocalVisualEmbeddingAdapter()
    # Reserved for future adapters: OpenAI-compatible / OrcaRouter.
    return UnavailableVisualEmbeddingAdapter()
