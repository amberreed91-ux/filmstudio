# SIX cast documents

Imported the supplied master cast JSON and heading-structured Word bible through a reusable deterministic importer. No LLM extraction or paid generation was required.

- JSON: 91 entries preserved, 89 mapped to cast profiles; the two collective/photo groups remain in reference planning. All 14 background groups and five referenced/archival declarations are preserved.
- DOCX: all 64 Heading 2 character sections preserved. 57 mapped to active profiles; seven preserved as reference sections.
- Profile appearance, personality, relationships, image prompts, and voice direction fill empty fields. Existing profile IDs, non-empty creative edits, assigned voices, and appearance approvals are retained.
- Complete source fields, including wardrobe, story function, arc, production recommendations, continuity notes, and general family/timeline rules, are accessible in The Page.
- Explicit original-file downloads are scoped to the selected project and verified byte-for-byte by SHA-256.
- Rayford's archival classification conflicts with his existing cast presence; both sources remain visible with a review note.
- No appearance or voice was automatically approved, and no images were generated.

Validation: 45 backend tests passed with USE_TORCH=0 to avoid an unrelated native Torch import abort in the test environment. Tests use a separate Harbor project, cover repeat imports, kinship-name separation, preservation of source fields, and project-scoped downloads. Frontend production build passed. The local backend was restarted and live reads confirmed both sources, 57 bible-enriched profiles, and 14 background groups.
