# Application update staging — not installation

Settings → Updates offers **Stage verified stable app** and cancellation through
the existing TaskManager worker lifecycle. Staging does not Apply unrelated
settings, stop downloads, launch a helper, replace an app, choose an installation
destination or publish a release. The UI reports bytes/status, last successful
**stage**, and redacted failures separately from component check/update times.

`AppUpdateManager.stage_latest` uses the fixed public
`MES30004E/mediagrabber/releases/latest` endpoint without a GitHub token or cookies.
Authoritative API metadata redirects are refused. Asset redirects may use only
the exact original GitHub repository/tag/asset URL or designated HTTPS GitHub
asset/CDN hosts. Duplicate JSON object members are rejected in both remote
documents, not silently resolved by last-key-wins parsing. Public metadata is
bounded; archive downloads stream in bounded chunks
with cancellation between reads and a 15-second socket timeout. This is not an
unbounded retry loop. HTTP403/429 retry/reset deadlines persist across restart,
and invalid saved deadlines cannot disable staging indefinitely.

## Accepted stable contract

- Non-draft, non-prerelease `vMAJOR.MINOR.PATCH`, strictly newer than installed.
- Exactly one uploaded `release.json` and one version/arm64 archive, with exact
  fixed repository/tag download URLs, positive bounded sizes and GitHub's
  `sha256:` asset digests. Missing/duplicated digest metadata fails closed.
- The manifest's downloaded bytes match GitHub's size/digest; the manifest has
  `channel: stable`, `publication_approved: true`, a valid source commit, matching
  version/archive name/size/SHA-256, Apple Silicon/macOS and minimum OS metadata.
- The current host must be arm64 macOS meeting the release's minimum version.
- Shared archive extraction rejects unsafe members/paths/symlinks and verifies
  bundle identity, version, executable architecture and strict deep signature.

The API metadata fields are documented by the official
[GitHub release-assets API](https://docs.github.com/en/rest/releases/assets?apiVersion=2026-03-10).
Checksums and repository-hosted metadata establish consistency, not independent
publisher identity. A manifest boolean is a consumer policy field, **not proof of
human approval**, Developer ID signing, notarisation or a protected CI promotion.
Those publishing controls must be implemented/qualified separately.

`build_development_archive` still only writes **development/unapproved** metadata.
`extract_development_archive` rejects stable manifests;
`extract_release_archive` rejects development manifests. No promotion or release
publication path is added by this consumer. There is no currently qualified
stable asset feed to claim live staging against; tests use synthetic releases.

## Persistence and failure behavior

The private runtime `app-updates` directory contains atomic mode0600 `state.json`
and successful `stage-UUID` candidates; its root is mode0700. A new stage is
published to the ledger only after integrity/compatibility/signature checks.
Failure/cancellation preserves the previous candidate and installation; a ledger
write failure removes only the operation's own uncommitted candidate. Concurrent
stage requests on one manager are rejected rather than spawning another download.
After restart the UI explicitly requires revalidation before installation. A
persisted path/last-stage timestamp alone never authorizes activation.

Successful stages are retained; retention/cleanup UI is not implemented. A
cancelled blocked read may need the socket timeout to finish; cancellation does
not kill threads. Existing TaskManager shutdown ownership stays in effect.

## Unfinished acceptance and priority

The hosted development archive signature failure was corrected by removing Canvas
compiler intermediates before normal signing. Exact commit `9a06044`, run
`40991415616`, passed strict extracted signature and real Cocoa launch checks;
there was no verification bypass or extracted-app re-signing. That validates the
development transport, not a live stable feed or independent publisher identity.

Post-exit coordination, durable crash journal, recovery/rollback UI, active-job
coordination, protected stable promotion, licence/source-offer/notices and actual
publication approval remain incomplete. The user deferred installation destination
resolution; no fallback path or additional launcher is selected. The external
exFAT target and bundle symlinks remain incompatible until explicitly resolved.

The newer P0 queue/crash requirements take priority after safely checkpointing
this existing work. See [FEATURE_BACKLOG.md](FEATURE_BACKLOG.md) for complete
acceptance criteria and remaining QA; this stager is not a finished app updater.

Portable tests: `tests/test_app_updates.py`, `tests/test_app_update_transport.py`,
`tests/test_app_updates_ui.py` and `tests/test_app_archives.py`. They use synthetic
metadata/media and injected native validation, not real account sessions, local
Apple build tools, a public release or the user's installation.
