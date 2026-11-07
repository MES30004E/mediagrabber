# Release readiness

Updated 2026-11-07. **Not ready for stable public release.** No release, uploaded
asset, user installation or notarisation is implied by CI success.

## Qualified development source

`e2f3ea33009610ae6bcf26dd06686ed33a539f33`, development branch
`improvement/download-reliability`; run42378146636 attempt2 passed all jobs.
The first packaging attempt timed out during a TLS source fetch; retrying that
job alone on unchanged source passed. No source pins/TLS/signature gates changed.
See QA_MATRIX.md and UI_CORRECTNESS.md for exact scope and limits.

Disposable hosted archive:141,966,769bytes,
SHA256 `647087b75db9a99ad09b6bf1051cf1eb21371fa0a25eb7595294332bbf12b095`.
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
