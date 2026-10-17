"""Deterministic character reference selection for provider payloads.

Purpose: identity preservation. When a provider accepts a bounded number of
reference images, the strongest *identity* evidence must claim the budget
before contextual (wardrobe / lighting / expression) references fill what is
left — and a night scene must not push Maya's face out of her own payload.

Design constraints (this module is deliberately boring):
- Deterministic: identical inputs produce an identical selection. No random
  tie-breaks, no timestamps in ordering, no hidden weighting. The only
  ordering inputs are the rows' existing registry metadata.
- Bounded: never returns more references than the provider budget.
- Auditable: every selection returns an audit trail — why each reference was
  chosen, why others were not — suitable for job metadata and structured
  logging. Nothing here is surfaced as a filmmaker-facing score.
- Additive: reads only existing ``reference_assets`` registry rows (canonical
  flag, kind, category, approval_state). It does not create a second registry,
  does not mutate rows, and does not use embeddings or computer vision.

Priority model, derived from the categories the Reference Library UI already
offers for characters (``face, profile, full_body, wardrobe, night,
expression``) plus the canonical flag:

  1. canonical anchor            (who the character IS — never displaced)
  2. face / identity             (kind=character_face, category=face)
  3. profile / side view         (category=profile)
  4. full body                   (category=full_body or kind=character_full)
  5. scene-context (night/day/lighting) — only when the scene calls for it,
     filling the first slot identity references did not use
  6. wardrobe
  7. expression
  8. other approved supporting references, registry order

Identity references establish who the character is; context references how
they should appear in this particular scene. Context can never outrank
identity: the scene-context tier sits strictly below the canonical/face/
profile/full-body tiers, so a night scene swaps its night reference in place
of the least identity-critical supporting references (the wardrobe/expression
slots) and never touches the identity anchors. With no matching context
reference the identity-first default selection stands.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

# ── Priority model ────────────────────────────────────────────────────────

# (tier_name, rank) — lower rank selects first. Tiers 1–5 are identity;
# tiers 6–8 are context/supporting. Kept as a tuple so iteration order is
# itself the documented priority.
IDENTITY_TIERS: tuple[tuple[str, int], ...] = (
    ("canonical", 0),
    ("face", 1),
    ("profile", 2),
    ("full_body", 3),
)
CONTEXT_TIERS: tuple[tuple[str, int], ...] = (
    ("scene_context", 4),
    ("wardrobe", 5),
    ("expression", 6),
    ("other", 7),
)

# Categories (and kinds) that resolve to each tier. Anything unmatched falls
# to the "other" tier — unknown future categories degrade gracefully instead
# of disappearing from selection.
_FACE_CATEGORIES = {"face", "facial", "headshot"}
_PROFILE_CATEGORIES = {"profile", "side", "side_view", "profile_view"}
_FULL_BODY_CATEGORIES = {"full_body", "fullbody", "body", "full"}
_EXPRESSION_CATEGORIES = {"expression", "expressions", "emotion"}
_WARDROBE_CATEGORIES = {"wardrobe", "costume", "outfit", "clothing"}

# Explicit category → tier, checked before any kind-based inference.
_CATEGORY_TIERS: dict[str, tuple[str, int]] = {
    **{category: ("face", 1) for category in _FACE_CATEGORIES},
    **{category: ("profile", 2) for category in _PROFILE_CATEGORIES},
    **{category: ("full_body", 3) for category in _FULL_BODY_CATEGORIES},
    **{category: ("wardrobe", 5) for category in _WARDROBE_CATEGORIES},
    **{category: ("expression", 6) for category in _EXPRESSION_CATEGORIES},
}

# Categories that describe context or provenance rather than identity
# evidence. A row in one of these never inherits an identity tier from its
# ``kind``: a full-body night shot is still a lighting reference, not a
# full-body identity anchor. When the scene calls for the matching condition
# the row is promoted to the scene_context tier instead.
_CONTEXT_OR_PROVENANCE_CATEGORIES = {
    "night", "day", "evening", "dawn", "dusk", "rain", "snow",
    "generated", "candidate", "detail", "other", "canonical", "general",
    "supporting",
}


def _tier_for_row(row: dict[str, Any]) -> tuple[str, int]:
    """Resolve a registry row's priority tier from its existing metadata.

    Uses only canonical/kind/category — the metadata already persisted on
    reference_assets. Order matters: the canonical flag outranks the row's own
    category, an explicit category outranks the generic ``character_full`` kind
    (which uploaded character references carry regardless of what they depict —
    the category is the real signal there), and kind is only a fallback for
    unlabeled rows.
    """
    if bool(row.get("canonical")):
        return "canonical", 0
    kind = str(row.get("kind") or "").strip().lower()
    category = str(row.get("category") or "").strip().lower()
    explicit = _CATEGORY_TIERS.get(category)
    if explicit is not None:
        return explicit
    if category in _CONTEXT_OR_PROVENANCE_CATEGORIES:
        return "other", 7
    if kind == "character_face":
        return "face", 1
    if kind == "character_full":
        return "full_body", 3
    return "other", 7


def _scene_context_rank(scene_categories: Iterable[str]) -> frozenset[str]:
    """Categories the current scene's conditions ask for (night, day, …)."""
    return frozenset(
        str(value or "").strip().lower()
        for value in (scene_categories or ())
        if str(value or "").strip()
    )


# ── Deduplication ─────────────────────────────────────────────────────────


def _url_signature(url: str) -> str:
    """Stable identity for a reference URL, tolerant of trivially different
    spellings of the same asset.

    Duplicate uploads land at distinct generated paths, so exact-URL dedup
    alone lets one image consume several provider slots. Matching on the
    normalized file name catches the common cases deterministically (the same
    file re-uploaded — upload tooling appends ``_2``/``-3``/``(1)``-style
    suffixes, and cache-busting query strings — without embeddings or visual
    comparison.
    """
    import re

    value = str(url or "").strip()
    if not value:
        return ""
    path = value.split("?", 1)[0].split("#", 1)[0]
    tail = path.rstrip("/").rsplit("/", 1)[-1].lower()
    # Collapse duplicate-upload suffixes: portrait_2.png, portrait-3.png,
    # portrait (1).png all compare equal to portrait.png.
    tail = re.sub(r"[ _\-]?\(\d+\)(?=\.[a-z0-9]+$)", "", tail)
    tail = re.sub(r"[ _\-]\d+(?=\.[a-z0-9]+$)", "", tail)
    return tail or path.lower()


# ── Selection ─────────────────────────────────────────────────────────────


@dataclass
class SelectionResult:
    """Selected references plus the audit trail explaining the selection."""

    selected: list[dict[str, Any]] = field(default_factory=list)
    audit: list[dict[str, Any]] = field(default_factory=list)
    excluded: list[dict[str, Any]] = field(default_factory=list)

    @property
    def urls(self) -> list[str]:
        return [str(row.get("image_url") or "") for row in self.selected]

    def summary(self) -> dict[str, Any]:
        """Compact, loggable selection record."""
        return {
            "selected": [
                {
                    "ref_id": row.get("ref_id"),
                    "tier": row.get("_selection_tier"),
                    "category": row.get("category") or "",
                    "canonical": bool(row.get("canonical")),
                    "reason": row.get("_selection_reason"),
                }
                for row in self.selected
            ],
            "excluded_count": len(self.excluded),
            "excluded": self.excluded,
        }


def select_character_references(
    rows: Iterable[dict[str, Any]],
    *,
    budget: int,
    scene_categories: Iterable[str] = (),
    character_name: str = "",
) -> SelectionResult:
    """Choose which character references reach the provider, in order.

    Parameters
    ----------
    rows:
        Approved ``reference_assets`` registry rows for ONE character, already
        filtered to approved state by the caller. Unapproved rows are skipped
        defensively anyway — a candidate or rejected reference must never reach
        the provider regardless of upstream filtering.
    budget:
        Provider reference slots available to this character.
    scene_categories:
        Scene conditions that may promote a contextual reference (e.g.
        ``["night"]`` for a night scene). Context never displaces identity:
        it only reorders supporting references into slots identity did not use.
    """
    result = SelectionResult()
    candidate_rows: list[dict[str, Any]] = []
    seen_signatures: set[str] = set()
    seen_urls: set[str] = set()

    # Pass 1 — eligibility + registry dedup, in the caller's stable order.
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        url = str(row.get("image_url") or "").strip()
        if not url:
            continue
        if str(row.get("approval_state") or "approved") != "approved":
            result.excluded.append({
                "ref_id": row.get("ref_id"),
                "reason": f"not approved (state={row.get('approval_state')})",
            })
            continue
        if url in seen_urls:
            result.excluded.append({
                "ref_id": row.get("ref_id"),
                "reason": "duplicate image_url already selected",
            })
            continue
        signature = _url_signature(url)
        if signature and signature in seen_signatures:
            result.excluded.append({
                "ref_id": row.get("ref_id"),
                "reason": "duplicate asset (same file) already selected",
            })
            continue
        seen_urls.add(url)
        if signature:
            seen_signatures.add(signature)
        candidate_rows.append(row)

    # Pass 2 — tier assignment. Stable sort on (rank, registry index): equal
    # tiers keep registry order, so the whole selection is deterministic.
    scene_context = _scene_context_rank(scene_categories)
    indexed: list[tuple[int, int, str, dict[str, Any]]] = []
    for index, row in enumerate(candidate_rows):
        tier, rank = _tier_for_row(row)
        # Scene-context promotion: a supporting reference matching the scene's
        # conditions (e.g. a night reference in a night scene) ranks directly
        # after the identity tiers — ahead of wardrobe/expression/other but
        # never ahead of the canonical anchor or any identity tier.
        if str(row.get("category") or "").strip().lower() in scene_context:
            tier, rank = "scene_context", 4
        indexed.append((rank, index, tier, row))
    indexed.sort(key=lambda item: (item[0], item[1]))

    # Pass 3 — budget fill. Identity tiers are always served before context
    # tiers because pass 2 already ordered them so.
    for rank, _index, tier, raw_row in indexed:
        if len(result.selected) >= max(0, budget):
            result.excluded.append({
                "ref_id": raw_row.get("ref_id"),
                "reason": "provider reference budget exhausted",
            })
            continue
        row = dict(raw_row)
        row["_selection_tier"] = tier
        row["_selection_rank"] = rank
        if tier == "canonical":
            row["_selection_reason"] = "canonical identity anchor — always first, never displaced"
        elif tier == "scene_context":
            row["_selection_reason"] = (
                "approved context reference matching this scene's conditions; "
                "selected only into slots identity references did not use"
            )
        else:
            row["_selection_reason"] = f"approved {tier.replace('_', ' ')} identity/supporting reference"
        result.selected.append(row)
        result.audit.append({
            "ref_id": row.get("ref_id"),
            "tier": tier,
            "image_url": row.get("image_url"),
            "reason": row["_selection_reason"],
        })

    if character_name:
        result.audit.insert(0, {"character": character_name, "budget": budget})
    return result


def scene_categories_for_prompt(prompt: str) -> list[str]:
    """Scene conditions implied by the render prompt, mapped onto the
    Reference Library's existing setting/character category vocabulary.

    Deliberately minimal and deterministic: keyword match on the prompt, no
    model calls, no ambiguity — an unknown condition yields no promotion and
    the identity-first default selection stands.
    """
    text = str(prompt or "").lower()
    conditions: list[str] = []
    if any(token in text for token in ("night", "midnight", "moonlit", "dark alley", "after dark")):
        conditions.append("night")
    if any(token in text for token in ("daylight", "daytime", "morning sun", "noon", "bright day")):
        conditions.append("day")
    return conditions
