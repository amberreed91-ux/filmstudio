"""Director's Memory Engine (v1).

Per-project, cross-session symbolic memory that tracks a filmmaker's
creative language across an entire film. Builds on the foundation of
Taste Memory v1 and Creative Decision Memory v1.

Rules (mirroring AGENTS.md memory guidelines):
- Co-director voice throughout — never produce numeric scores or percentages.
- Explicit-save-only for user-defined entries (symbols, characters, themes,
  director's notes). Motif detection may be session-only (advisory).
- Storage is delegated to ``project_store`` (per-project JSON).
- Thin service: pure functions over project state, no provider calls.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

from app.services.project_store import project_store


# Entry kinds tracked by the engine.
ENTRY_KINDS: Tuple[str, ...] = ("symbols", "motifs", "characters", "themes", "notes", "debates")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_scene_label(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _coerce_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _entry_summary_label(kind: str, entry: Dict[str, Any]) -> str:
    """Human-readable short label used in co-director callbacks."""
    if kind == "symbols":
        sym = entry.get("symbol") or "(unnamed symbol)"
        meaning = entry.get("meaning") or ""
        return f"{sym}" + (f" ({meaning})" if meaning else "")
    if kind == "motifs":
        return str(entry.get("motif") or entry.get("name") or "(unnamed motif)")
    if kind == "characters":
        return str(entry.get("character") or entry.get("name") or "(unnamed character)")
    if kind == "themes":
        return str(entry.get("theme") or entry.get("name") or "(unnamed theme)")
    if kind == "notes":
        # Director's notes use the headline if present, otherwise truncated body.
        headline = str(entry.get("headline") or "").strip()
        if headline:
            return headline
        body = str(entry.get("note") or "").strip()
        return body[:48] + ("…" if len(body) > 48 else "")
    return "(entry)"


class DirectorMemoryService:
    """Pure-Python service. Storage delegated to ``project_store``."""

    # ------------------------------------------------------------------ #
    # Read helpers
    # ------------------------------------------------------------------ #

    def get_memory(self, project_id: str) -> Dict[str, List[Dict[str, Any]]]:
        """Return the full director memory bundle for a project.

        Always returns a dict with every entry kind present (possibly empty).
        """
        bundle = project_store.get_director_memory(project_id)
        for kind in ENTRY_KINDS:
            bundle.setdefault(kind, [])
            if not isinstance(bundle[kind], list):
                bundle[kind] = []
        return bundle

    def list_entries(self, project_id: str, kind: str) -> List[Dict[str, Any]]:
        if kind not in ENTRY_KINDS:
            raise ValueError(f"unknown director memory kind: {kind}")
        return list(self.get_memory(project_id).get(kind, []))

    # ------------------------------------------------------------------ #
    # Write helpers
    # ------------------------------------------------------------------ #

    def save_entry(
        self,
        project_id: str,
        kind: str,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Save a new entry of the given kind. Explicit-save-only."""
        if kind not in ENTRY_KINDS:
            raise ValueError(f"unknown director memory kind: {kind}")

        normalized = self._normalize_payload(kind, payload)
        return project_store.save_director_memory_entry(project_id, kind, normalized)

    def update_entry(
        self,
        project_id: str,
        kind: str,
        entry_id: str,
        updates: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        if kind not in ENTRY_KINDS:
            raise ValueError(f"unknown director memory kind: {kind}")
        # Filter to known editable fields only.
        editable = self._editable_fields(kind)
        clean = {k: v for k, v in (updates or {}).items() if k in editable}
        return project_store.update_director_memory_entry(
            project_id, kind, entry_id, clean
        )

    def delete_entry(self, project_id: str, kind: str, entry_id: str) -> bool:
        if kind not in ENTRY_KINDS:
            raise ValueError(f"unknown director memory kind: {kind}")
        return project_store.delete_director_memory_entry(project_id, kind, entry_id)

    # ------------------------------------------------------------------ #
    # Co-director scanning
    # ------------------------------------------------------------------ #

    def scan_scene(
        self,
        project_id: str,
        scene: Dict[str, Any],
        *,
        scene_index: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Scan a scene against memory and produce advisory callbacks.

        Output is co-director voice — never numeric scores or percentages.
        Returns a dict ``{callbacks: [...], scene_id, scene_index}``.
        """
        memory = self.get_memory(project_id)
        scene_id = _normalize_scene_label(scene.get("scene_id") or scene.get("id"))
        current_index = self._coerce_scene_index(scene, scene_index)
        haystack = self._scene_text(scene).lower()

        callbacks: List[Dict[str, Any]] = []

        # Symbols — mention each user-defined symbol with absence framing.
        for entry in _coerce_list(memory.get("symbols")):
            sym = str(entry.get("symbol") or "").strip()
            if not sym:
                continue
            if sym.lower() in haystack:
                callbacks.append(
                    self._callback(
                        kind="symbols",
                        entry=entry,
                        message=(
                            f"The {sym} motif "
                            f"({entry.get('meaning') or 'meaning unset'}) "
                            f"appears here. Consider how it carries the film's emotional thread."
                        ),
                        scene_id=scene_id,
                    )
                )
                # Update last_seen_scene quietly.
                self._touch_last_seen(project_id, "symbols", entry, scene_id)
            else:
                last_seen = entry.get("last_seen_scene") or entry.get("first_introduced_scene")
                last_index = self._scene_label_to_index(last_seen)
                if (
                    current_index is not None
                    and last_index is not None
                    and current_index - last_index >= 3
                ):
                    callbacks.append(
                        self._callback(
                            kind="symbols",
                            entry=entry,
                            message=(
                                f"The {sym} motif "
                                f"({entry.get('meaning') or 'meaning unset'}) "
                                f"has not appeared since {last_seen}. "
                                f"Reintroducing it here may strengthen the emotional arc."
                            ),
                            scene_id=scene_id,
                        )
                    )

        # Visual motifs — same absence logic, lighter framing.
        for entry in _coerce_list(memory.get("motifs")):
            label = _entry_summary_label("motifs", entry)
            keyword = str(entry.get("keyword") or entry.get("motif") or "").strip().lower()
            if keyword and keyword in haystack:
                callbacks.append(
                    self._callback(
                        kind="motifs",
                        entry=entry,
                        message=f"The visual motif “{label}” surfaces here again.",
                        scene_id=scene_id,
                    )
                )
                self._touch_last_seen(project_id, "motifs", entry, scene_id)
            else:
                last_seen = entry.get("last_seen_scene")
                last_index = self._scene_label_to_index(last_seen)
                if (
                    current_index is not None
                    and last_index is not None
                    and current_index - last_index >= 4
                ):
                    callbacks.append(
                        self._callback(
                            kind="motifs",
                            entry=entry,
                            message=(
                                f"The visual motif “{label}” has been absent "
                                f"for several scenes — worth a deliberate beat here?"
                            ),
                            scene_id=scene_id,
                        )
                    )

        # Characters — flag out-of-character moments.
        for entry in _coerce_list(memory.get("characters")):
            name = str(entry.get("character") or entry.get("name") or "").strip()
            if not name or name.lower() not in haystack:
                continue
            avoids = [str(t).strip().lower() for t in _coerce_list(entry.get("avoids")) if str(t).strip()]
            traits = [str(t).strip().lower() for t in _coerce_list(entry.get("traits")) if str(t).strip()]
            triggered_avoid = [a for a in avoids if a and a in haystack]
            if triggered_avoid:
                callbacks.append(
                    self._callback(
                        kind="characters",
                        entry=entry,
                        message=(
                            f"{name} has avoided “{triggered_avoid[0]}” in every prior scene. "
                            f"This moment marks a significant character shift — intentional?"
                        ),
                        scene_id=scene_id,
                    )
                )
            elif traits and not any(t in haystack for t in traits):
                callbacks.append(
                    self._callback(
                        kind="characters",
                        entry=entry,
                        message=(
                            f"{name} appears here without their established voice "
                            f"({', '.join(traits)}). Worth a second pass?"
                        ),
                        scene_id=scene_id,
                    )
                )

        # Themes — surface long absences.
        for entry in _coerce_list(memory.get("themes")):
            theme = str(entry.get("theme") or entry.get("name") or "").strip()
            if not theme:
                continue
            if theme.lower() in haystack:
                callbacks.append(
                    self._callback(
                        kind="themes",
                        entry=entry,
                        message=f"The theme of {theme} resurfaces here.",
                        scene_id=scene_id,
                    )
                )
                self._touch_last_seen(project_id, "themes", entry, scene_id)
            else:
                last_seen = entry.get("last_seen_scene")
                last_index = self._scene_label_to_index(last_seen)
                if (
                    current_index is not None
                    and last_index is not None
                    and current_index - last_index >= 3
                ):
                    gap = current_index - last_index
                    callbacks.append(
                        self._callback(
                            kind="themes",
                            entry=entry,
                            message=(
                                f"{theme.capitalize()} last appeared in {last_seen} — "
                                f"{gap} scenes ago."
                            ),
                            scene_id=scene_id,
                        )
                    )

        # Director's notes — surface relevant pinned notes when keywords match.
        for entry in _coerce_list(memory.get("notes")):
            keyword = str(entry.get("keyword") or "").strip().lower()
            if keyword and keyword in haystack:
                callbacks.append(
                    self._callback(
                        kind="notes",
                        entry=entry,
                        message=(
                            f"Director's note — {_entry_summary_label('notes', entry)}: "
                            f"{entry.get('note') or ''}".strip()
                        ),
                        scene_id=scene_id,
                    )
                )

        return {
            "project_id": project_id,
            "scene_id": scene_id,
            "scene_index": current_index,
            "callbacks": callbacks,
            "generated_at": _now_iso(),
        }

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _callback(*, kind: str, entry: Dict[str, Any], message: str, scene_id: str) -> Dict[str, Any]:
        return {
            "kind": kind,
            "entry_id": entry.get("entry_id"),
            "label": _entry_summary_label(kind, entry),
            "message": message,
            "scene_id": scene_id,
            "voice": "co_director",
        }

    @staticmethod
    def _scene_text(scene: Dict[str, Any]) -> str:
        parts: List[str] = []
        for key in ("title", "heading", "slugline", "summary", "description", "text", "content", "body"):
            value = scene.get(key)
            if isinstance(value, str):
                parts.append(value)
        beats = scene.get("beats")
        if isinstance(beats, list):
            for beat in beats:
                if isinstance(beat, str):
                    parts.append(beat)
                elif isinstance(beat, dict):
                    for v in beat.values():
                        if isinstance(v, str):
                            parts.append(v)
        return "\n".join(parts)

    @staticmethod
    def _coerce_scene_index(scene: Dict[str, Any], explicit: Optional[int]) -> Optional[int]:
        if explicit is not None:
            try:
                return int(explicit)
            except (TypeError, ValueError):
                pass
        for key in ("scene_index", "index", "scene_number", "number", "order"):
            v = scene.get(key)
            try:
                if v is not None:
                    return int(v)
            except (TypeError, ValueError):
                continue
        sid = str(scene.get("scene_id") or "")
        digits = "".join(ch for ch in sid if ch.isdigit())
        if digits:
            try:
                return int(digits)
            except ValueError:
                return None
        return None

    @staticmethod
    def _scene_label_to_index(label: Any) -> Optional[int]:
        if label is None:
            return None
        text = str(label)
        digits = "".join(ch for ch in text if ch.isdigit())
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    def _touch_last_seen(
        self,
        project_id: str,
        kind: str,
        entry: Dict[str, Any],
        scene_id: str,
    ) -> None:
        if not scene_id:
            return
        entry_id = entry.get("entry_id")
        if not entry_id:
            return
        try:
            project_store.update_director_memory_entry(
                project_id,
                kind,
                str(entry_id),
                {"last_seen_scene": scene_id},
                _allow_system_fields=True,
            )
        except Exception:
            # Best-effort — never let memory tracking break the scan response.
            return

    @staticmethod
    def _editable_fields(kind: str) -> Iterable[str]:
        common = {"last_seen_scene"}
        if kind == "symbols":
            return common | {"symbol", "meaning", "first_introduced_scene"}
        if kind == "motifs":
            return common | {"motif", "name", "keyword", "first_introduced_scene"}
        if kind == "characters":
            return common | {"character", "name", "traits", "avoids", "motivations", "speech_patterns"}
        if kind == "themes":
            return common | {"theme", "name", "first_introduced_scene"}
        if kind == "notes":
            return common | {"headline", "note", "keyword"}
        return common

    @staticmethod
    def _normalize_payload(kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if kind == "symbols":
            symbol = str(payload.get("symbol") or "").strip()
            if not symbol:
                raise ValueError("symbol is required")
            data["symbol"] = symbol
            data["meaning"] = str(payload.get("meaning") or "").strip()
            data["first_introduced_scene"] = _normalize_scene_label(
                payload.get("first_introduced_scene") or payload.get("scene_id")
            )
            data["last_seen_scene"] = _normalize_scene_label(
                payload.get("last_seen_scene") or data["first_introduced_scene"]
            )
        elif kind == "motifs":
            motif = str(payload.get("motif") or payload.get("name") or "").strip()
            if not motif:
                raise ValueError("motif is required")
            data["motif"] = motif
            data["keyword"] = str(payload.get("keyword") or motif).strip()
            data["first_introduced_scene"] = _normalize_scene_label(
                payload.get("first_introduced_scene") or payload.get("scene_id")
            )
            data["last_seen_scene"] = _normalize_scene_label(
                payload.get("last_seen_scene") or data["first_introduced_scene"]
            )
        elif kind == "characters":
            name = str(payload.get("character") or payload.get("name") or "").strip()
            if not name:
                raise ValueError("character is required")
            data["character"] = name
            data["traits"] = [str(t).strip() for t in _coerce_list(payload.get("traits")) if str(t).strip()]
            data["avoids"] = [str(t).strip() for t in _coerce_list(payload.get("avoids")) if str(t).strip()]
            data["motivations"] = str(payload.get("motivations") or "").strip()
            data["speech_patterns"] = str(payload.get("speech_patterns") or "").strip()
        elif kind == "themes":
            theme = str(payload.get("theme") or payload.get("name") or "").strip()
            if not theme:
                raise ValueError("theme is required")
            data["theme"] = theme
            data["first_introduced_scene"] = _normalize_scene_label(
                payload.get("first_introduced_scene") or payload.get("scene_id")
            )
            data["last_seen_scene"] = _normalize_scene_label(
                payload.get("last_seen_scene") or data["first_introduced_scene"]
            )
        elif kind == "notes":
            note = str(payload.get("note") or "").strip()
            if not note:
                raise ValueError("note is required")
            data["headline"] = str(payload.get("headline") or "").strip()
            data["note"] = note
            data["keyword"] = str(payload.get("keyword") or "").strip()
        return data


director_memory_service = DirectorMemoryService()
