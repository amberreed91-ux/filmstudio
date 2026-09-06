# Casting options design implementation

Casting stays in The Page’s existing third step, before storyboarding. The saved physical profile introduces a restrained casting action, optional direction disclosure, and three-portrait contact sheet. Selection is distinct from approval. New sets preserve earlier options behind a disclosure; partial and earlier-profile results have explicit review guidance. Locked looks only expose generation again after deliberate reopening.

The layout keeps a generous selected portrait beside the profile and contact sheet on desktop. On mobile it reads in production order: saved profile, casting options, selected portrait or upload, approval. Secondary render wording, full-body reference and previous references remain available through disclosures. Charcoal, ivory and amber inherit the studio’s current visual language.

## Modified application files

- `studio-app/src/components/CharacterLookApproval.tsx`: casting controls, incremental result presentation, state guidance, mobile reading order and explicit approval footer.
- `studio-app/src/pages/WritersRoom.tsx`: three short copy changes explaining casting after profiles and before storyboard.

Backend, contracts and hooks were implemented separately by the root agent.

## Verification

`/tmp/playwright-test-casting-generation.js` ran against the real Vite page at `http://localhost:5001`, with every mutation intercepted. Thirteen browser checks passed, zero page errors, four intercepted writes. No provider was called and no film data was changed. The image fixtures are existing local rendered character frames standing in for casting portraits.

Verified deep link, transport-error recovery via read without another POST, reload during generation, switching characters while polling, incremental results, retained selection across polls, explicit approval, lock/reopen, partial and failed sets, earlier-profile labeling, uploads, unsaved-profile guard and age-only disablement. Desktop and 390-pixel mobile screenshots have no horizontal overflow. Cross-project polling was not exercised by this browser fixture.

ESLint: no errors in either changed file. Three existing WritersRoom hook-dependency warnings remain.

Detailed assertions and intercepted request payloads: `browser-verification.json`.

Representative screenshots:

- `casting-desktop-options.png`
- `casting-mobile-options.png`
- `casting-mobile-selected.png`
- `casting-desktop-progress.png`
- `casting-desktop-partial-stale.png`
- `casting-desktop-failed.png`
- `casting-mobile-locked.png`
