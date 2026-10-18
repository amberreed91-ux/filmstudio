# Full-script cast reconciliation

Applied to SIX (project_752ca3944869). The Page now discovers cast from the entire saved screenplay, independently of previously saved scene character arrays. Discovery includes named action introductions, silent named characters, speaking roles, phone/off-screen cues, names wrapped across lines, and explicit nicknames. Unambiguous plain full names and introduction-backed surname cues share the same matching path. Ambiguous identities remain separate.

The explicit Refresh cast from full script action creates missing profiles and reconciles names. It preserves existing profile IDs and fields, leaves locked appearances alone, and flags conflicting populated profiles. Empty duplicate deletion checks the original revision, profile contents, SQLite references including JSON, and project-state references. Reads do not create records.

## Applied data repair

- 71 profiles before; 80 after.
- 11 missing profiles added; 30 names reconciled.
- Removed the unreferenced empty MAK duplicate, preserving the imported Malcolm profile's ID and every non-name field.
- Removed the empty collective cue ALL FIVE BROTHERS, which is not an additional person.
- No unresolved merge conflicts; no missing profiles against the discovered cast.
- Full rows saved in profiles-before.json and profiles-after.json. Results saved in reconciliation.json.
- Original script and existing scene breakdown were not rewritten.

## Verification

582 backend tests passed before the final collective-cue safeguard; the focused 29-test suite then passed including that safeguard. 44 frontend API tests passed. Production build and git diff --check passed. Restarted the idle local backend and verified readiness, 80 live profiles, and zero missing profiles from the live discovery endpoint; see live-activation.json.

Cast discovery is based on screenplay cues and explicit introductions. It does not assign names to anonymous background people or infer identities from a shared surname alone.
