# Release readiness

Updated 2026-11-07. **Not ready for stable public release.** No release, uploaded
asset, user installation or notarisation is implied by CI success.

## Qualified development source

`380e62b4b1cc6e321dbc9656dc4f6030a9650918`, development branch
`improvement/download-reliability`; run42382032289 attempt1 passed all jobs.
Actual native/frozen/archive reports inspected and strict four-size validator
rerun. See QA_MATRIX.md and DISPATCH_CAPACITY.md for exact scope and limits.

Disposable hosted archive:141,968,028bytes,
SHA256 `13e3027c0705d27be304c71777b08316e39f4c5a017cc51f575990d4848a2239`.
Strict signature and content/symlink/mode round-trip, extracted launch and owned
replacement/backup passed. This is an ad-hoc development build, not Developer ID
signing or notarisation. No artefact was published or installed.

## Release blockers

- Q01/Q11: remaining multi-second GUI gaps and long-lived retention unresolved.
- Q08–Q10: complete duplicate/archive, interruption and queued-edit acceptance.
- U/RB/V: professional design, full visible rebrand and genuine local playback.
- D/AU/M/F: user-participating authenticated downloads, safe scoped lifetimes,
  first-run setup and route/privacy acceptance; never request raw credentials.
- R02/R05/R06: qualified component activation, stop-coordinated app replacement,
  durable failure recovery/rollback and data/session preservation.
- R07/R08: application licence/source-offer/third-party notices, supported native
  platform/codec/new-user matrix, signing/notarisation decisions and explicit
  release approval. Existing validation workflow is not a release workflow.
- Installation destination: preferred external exFAT bundle path unresolved;
  framework symlink support must be demonstrated, not assumed. No move/install
  to that path or /Applications and no Desktop launcher without approval.

## Publication gates

Reviewed exact source; targeted/full/native/packaged QA; full local allrefs/reflogs/
history, provider and exact-index secret scans; verify Public visibility. Known
scanner hits are a public Chrome identity key and two upstream anonymous constants,
not blanket suppressions. Any new finding must be investigated before pushing.
Keep private settings/cookies/keys/downloads/runtime/build outputs out of Git.

Development pushes may proceed after audit. Do not force-push, merge main, modify
protected Swift branches, repin the provider, publish assets/releases or replace
an installed app without the applicable explicit approval. No local admin/Xcode/
licence-gated build/signing tools. Hosted CI owns native packaging.
