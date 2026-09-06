from __future__ import annotations

import base64
import hashlib
import logging
import mimetypes
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


# ── Embedding kinds ──────────────────────────────────────────────────────────
#
# These are not interchangeable and must never be compared to each other.
#
# A general-visual embedding (CLIP-family, e.g. DashScope multimodal-embedding)
# encodes the whole picture: setting, palette, wardrobe, framing. Two different
# actors photographed in the same kitchen under the same light score high on it.
# It is a good continuity signal and a WEAK identity signal.
#
# A face-identity embedding (ArcFace-family) encodes facial geometry and is
# trained specifically so the same person scores high across lighting, pose, and
# expression while different people score low. It is the right tool for "is this
# the same character", and its cosine values live on a completely different
# scale from CLIP's.
#
# Thresholds are therefore defined per kind, not globally.
EMBEDDING_KIND_FACE = "face_identity"
EMBEDDING_KIND_VISUAL = "general_visual"
EMBEDDING_KIND_OPAQUE = "opaque"

# (consistent_at_or_above, plausibly_consistent_at_or_above)
#
# Face thresholds follow standard ArcFace verification practice on L2-normalised
# embeddings: same-person pairs cluster well above ~0.45, different-person pairs
# below ~0.30.
#
# Visual thresholds are deliberately strict because same-scene frames of
# *different* people already score high on CLIP — a high score here means "the
# frame did not change much", which is weaker evidence and is labelled as such
# by callers.
SIMILARITY_THRESHOLDS: Dict[str, tuple[float, float]] = {
    EMBEDDING_KIND_FACE: (0.55, 0.38),
    EMBEDDING_KIND_VISUAL: (0.93, 0.85),
    EMBEDDING_KIND_OPAQUE: (0.97, 0.82),
}


def similarity_thresholds(kind: str) -> tuple[float, float]:
    return SIMILARITY_THRESHOLDS.get(kind, SIMILARITY_THRESHOLDS[EMBEDDING_KIND_OPAQUE])


def match_label(similarity: float, kind: str) -> str:
    """Classify a cosine similarity against the thresholds for its embedding kind."""
    consistent_at, plausible_at = similarity_thresholds(kind)
    if similarity >= consistent_at:
        return "consistent"
    if similarity >= plausible_at:
        return "plausibly_consistent"
    return "identity_drift"


@dataclass
class VisualEmbeddingResult:
    vector: List[float]
    dimension: int
    provider: str
    model: str
    status: str
    metadata: Dict[str, object] = field(default_factory=dict)
    # What this vector actually measures. Callers must not compare vectors of
    # different kinds, and must pick thresholds by kind.
    kind: str = EMBEDDING_KIND_OPAQUE


class VisualEmbeddingAdapter:
    #: Overridden by concrete adapters.
    kind: str = EMBEDDING_KIND_OPAQUE

    def embed_image(self, image_path: str, context: Optional[Dict[str, object]] = None) -> VisualEmbeddingResult:
        raise NotImplementedError


class UnavailableVisualEmbeddingAdapter(VisualEmbeddingAdapter):
    kind = EMBEDDING_KIND_OPAQUE

    def embed_image(self, image_path: str, context: Optional[Dict[str, object]] = None) -> VisualEmbeddingResult:
        return VisualEmbeddingResult(
            vector=[],
            dimension=0,
            provider="unavailable",
            model="unconfigured",
            status="unavailable",
            metadata={"message": "visual embedding provider not configured"},
            kind=EMBEDDING_KIND_OPAQUE,
        )


class MockLocalVisualEmbeddingAdapter(VisualEmbeddingAdapter):
    """Deterministic local embedding adapter for safe QA/testing.

    This hashes the file's bytes. Two frames of the same actor one pixel apart
    produce uncorrelated vectors, so it measures nothing about identity — it
    exists only so tests have a stable, offline, zero-cost vector source. It is
    never selected automatically; VISUAL_EMBEDDING_PROVIDER must ask for it by
    name.
    """

    kind = EMBEDDING_KIND_OPAQUE

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
                kind=EMBEDDING_KIND_OPAQUE,
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
            metadata={
                "advisory_only": True,
                "external_call": False,
                "measures_identity": False,
                "context": context or {},
            },
            kind=EMBEDDING_KIND_OPAQUE,
        )


def _read_image_as_data_url(path: Path) -> str:
    mime_type, _ = mimetypes.guess_type(path.name)
    if mime_type not in {"image/jpeg", "image/png", "image/webp", "image/bmp"}:
        mime_type = "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class DashScopeMultimodalEmbeddingAdapter(VisualEmbeddingAdapter):
    """Hosted general-visual embeddings via DashScope multimodal-embedding.

    Uses the DashScope key already configured for Qwen / HappyHorse / CosyVoice,
    so it adds no new credential and no new Python dependency.

    Only images are sent — never screenplay text — so this path is not affected
    by the tenant policy that blocks screenplay content on live DashScope calls.

    Reminder on interpretation: this is a general-visual embedding. High
    similarity means the frames look alike, which is continuity evidence rather
    than proof of the same face. For identity, prefer the face adapter.
    """

    kind = EMBEDDING_KIND_VISUAL

    DEFAULT_MODEL = "multimodal-embedding-v1"
    ENDPOINT_PATH = "/services/embeddings/multimodal-embedding/multimodal-embedding"

    def __init__(self, model: str | None = None, timeout_seconds: float = 30.0):
        self._model = (model or os.getenv("VISUAL_EMBEDDING_MODEL") or self.DEFAULT_MODEL).strip()
        self._timeout = timeout_seconds

    def _unavailable(self, message: str, **extra: object) -> VisualEmbeddingResult:
        return VisualEmbeddingResult(
            vector=[],
            dimension=0,
            provider="dashscope",
            model=self._model,
            status="unavailable",
            metadata={"message": message, **extra},
            kind=self.kind,
        )

    def embed_image(self, image_path: str, context: Optional[Dict[str, object]] = None) -> VisualEmbeddingResult:
        path = Path(image_path)
        if not path.exists() or not path.is_file():
            return self._unavailable("image file not accessible", path=image_path)

        try:
            from app.services.shared.dashscope_client import get_dashscope_config

            config = get_dashscope_config()
        except Exception as exc:
            return self._unavailable(f"dashscope config unavailable: {exc}")

        try:
            import httpx
        except Exception as exc:  # pragma: no cover - httpx is a declared dependency
            return self._unavailable(f"httpx unavailable: {exc}")

        url = f"{config.native_api_base_url}{self.ENDPOINT_PATH}"
        payload = {
            "model": self._model,
            "input": {"contents": [{"image": _read_image_as_data_url(path)}]},
        }
        headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }

        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=self._timeout)
            if response.status_code != 200:
                return self._unavailable(
                    f"dashscope embedding HTTP {response.status_code}",
                    body=response.text[:400],
                )
            body = response.json()
        except Exception as exc:
            return self._unavailable(f"dashscope embedding call failed: {exc}")

        vector = self._extract_vector(body)
        if not vector:
            return self._unavailable("dashscope embedding response contained no vector")

        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        normalised = [value / norm for value in vector]
        return VisualEmbeddingResult(
            vector=normalised,
            dimension=len(normalised),
            provider="dashscope",
            model=self._model,
            status="complete",
            metadata={
                "external_call": True,
                "measures_identity": False,
                "context": context or {},
            },
            kind=self.kind,
        )

    @staticmethod
    def _extract_vector(body: object) -> List[float]:
        if not isinstance(body, dict):
            return []
        output = body.get("output")
        if not isinstance(output, dict):
            return []
        embeddings = output.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            return []
        first = embeddings[0]
        if not isinstance(first, dict):
            return []
        raw = first.get("embedding")
        if not isinstance(raw, list):
            return []
        values: List[float] = []
        for item in raw:
            try:
                values.append(float(item))
            except (TypeError, ValueError):
                return []
        return values


class LocalFaceEmbeddingAdapter(VisualEmbeddingAdapter):
    """Local face-identity embeddings via InsightFace.

    This is the adapter that can actually answer "is this the same person".
    It is optional: `insightface` and `onnxruntime` are not in requirements.txt,
    because they pull ~200MB of model weights. Install them and identity
    verification upgrades from continuity evidence to a real likeness measure:

        pip install insightface onnxruntime

    Runs entirely locally — no provider spend, no image leaves the machine,
    unaffected by tenant policy.
    """

    kind = EMBEDDING_KIND_FACE

    DEFAULT_MODEL = "buffalo_l"

    def __init__(self, model: str | None = None):
        self._model = (model or os.getenv("VISUAL_EMBEDDING_FACE_MODEL") or self.DEFAULT_MODEL).strip()
        self._app = None

    @staticmethod
    def is_available() -> bool:
        try:
            import importlib.util

            return (
                importlib.util.find_spec("insightface") is not None
                and importlib.util.find_spec("onnxruntime") is not None
            )
        except Exception:
            return False

    def _unavailable(self, message: str, **extra: object) -> VisualEmbeddingResult:
        return VisualEmbeddingResult(
            vector=[],
            dimension=0,
            provider="insightface",
            model=self._model,
            status="unavailable",
            metadata={"message": message, **extra},
            kind=self.kind,
        )

    def _analyzer(self):
        if self._app is not None:
            return self._app
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(name=self._model, providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=(640, 640))
        self._app = app
        return app

    def embed_image(self, image_path: str, context: Optional[Dict[str, object]] = None) -> VisualEmbeddingResult:
        path = Path(image_path)
        if not path.exists() or not path.is_file():
            return self._unavailable("image file not accessible", path=image_path)

        try:
            import numpy as np
            from PIL import Image
        except Exception as exc:
            return self._unavailable(f"numpy/Pillow unavailable: {exc}")

        try:
            analyzer = self._analyzer()
        except Exception as exc:
            return self._unavailable(f"insightface unavailable: {exc}")

        try:
            with Image.open(path) as image:
                # InsightFace expects BGR, Pillow gives RGB.
                array = np.asarray(image.convert("RGB"))[:, :, ::-1]
            faces = analyzer.get(array)
        except Exception as exc:
            return self._unavailable(f"face analysis failed: {exc}")

        if not faces:
            # A frame with no detectable face cannot answer an identity question.
            # Saying so is the correct outcome; a zero vector would read as drift.
            return self._unavailable("no face detected in frame", path=str(path))

        # Largest detected face — in a character reference frame the subject is
        # the foreground face, not a passer-by in the background.
        def _area(face) -> float:
            box = getattr(face, "bbox", None)
            if box is None or len(box) < 4:
                return 0.0
            return float(abs(box[2] - box[0]) * abs(box[3] - box[1]))

        best_face = max(faces, key=_area)
        raw = getattr(best_face, "normed_embedding", None)
        if raw is None:
            raw = getattr(best_face, "embedding", None)
        if raw is None:
            return self._unavailable("face detected but no embedding returned")

        vector = [float(value) for value in raw]
        norm = sum(value * value for value in vector) ** 0.5 or 1.0
        normalised = [value / norm for value in vector]

        return VisualEmbeddingResult(
            vector=normalised,
            dimension=len(normalised),
            provider="insightface",
            model=self._model,
            status="complete",
            metadata={
                "external_call": False,
                "measures_identity": True,
                "faces_detected": len(faces),
                "context": context or {},
            },
            kind=self.kind,
        )


def _dashscope_is_configured() -> bool:
    try:
        from app.services.shared.dashscope_client import get_dashscope_config

        return bool(get_dashscope_config().api_key)
    except Exception:
        return False


def build_visual_embedding_adapter() -> VisualEmbeddingAdapter:
    """Select the visual embedding adapter.

    `VISUAL_EMBEDDING_PROVIDER` forces a choice. With nothing set, this
    auto-detects rather than defaulting to Unavailable — the previous default
    meant every identity comparison silently returned empty vectors, which
    `_cosine` turned into 0.0, i.e. permanent "identity_drift" that no one saw
    because nothing consumed the result.

    Preference order when auto-detecting: local face identity (most accurate,
    no spend, no data leaves the machine) → hosted general-visual → unavailable.
    """
    provider = (os.getenv("VISUAL_EMBEDDING_PROVIDER") or "").strip().lower()

    if provider in {"mock", "mock_local", "local"}:
        return MockLocalVisualEmbeddingAdapter()
    if provider in {"face", "insightface", "arcface"}:
        return LocalFaceEmbeddingAdapter()
    if provider in {"dashscope", "qwen", "multimodal"}:
        return DashScopeMultimodalEmbeddingAdapter()
    if provider in {"none", "unavailable", "off", "disabled"}:
        return UnavailableVisualEmbeddingAdapter()
    if provider:
        logger.warning(
            "VISUAL_EMBEDDING_PROVIDER=%r is not recognised; falling back to auto-detection",
            provider,
        )

    if LocalFaceEmbeddingAdapter.is_available():
        logger.info("VISUAL_EMBEDDING_ADAPTER | selected=insightface (auto)")
        return LocalFaceEmbeddingAdapter()
    if _dashscope_is_configured():
        logger.info("VISUAL_EMBEDDING_ADAPTER | selected=dashscope (auto)")
        return DashScopeMultimodalEmbeddingAdapter()

    logger.info("VISUAL_EMBEDDING_ADAPTER | selected=unavailable (auto; nothing configured)")
    return UnavailableVisualEmbeddingAdapter()
