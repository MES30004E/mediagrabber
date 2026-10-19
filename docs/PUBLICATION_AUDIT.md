# Local publication audit — 18 October 2026

Scope: local application Git refs/reflogs/history and the full staged source
snapshot before publication of `improvement/download-reliability`; separate
inspection of the pinned provider's nested local Git history. This does not
claim a hosted GitHub secret-scanning result or make generated user data public.

## Tool and commands

Gitleaks **8.30.1**, official darwin_arm64 release archive, verified against the
official release checksums before extraction/execution. Tool and redacted JSON
reports are ignored under `.tools/`, not source or release artifacts.

```sh
gitleaks git --log-opts='--all --reflog --full-history' --redact --no-banner \
  --report-format=json --report-path=<private-report> .
gitleaks git --log-opts='--all --reflog --full-history' --redact --no-banner \
  --report-format=json --report-path=<private-provider-report> bgutil-ytdlp-pot-provider
gitleaks dir --redact --no-banner --report-format=json \
  --report-path=<private-index-report> <fresh-checkout-index-export>
```

Use the standalone Git in PATH on the licence-gated local Mac. Export the index
into a fresh temporary directory with `git checkout-index --all --prefix=.../`;
do not scan/upload a real browser profile, Keychain export, local settings or
download directory. The source export intentionally excludes ignored tooling and
untracked Phase 3 plan drafts. Scan raw findings with redaction; never print an
unredacted credential value to logs or chat.

## Findings and explicit triage

- Initial root scan: **19 commits**, matching `git rev-list --all --reflog
  --count`; 971,133 bytes of historical changes. One generic-api-key finding:
  `companion/chrome/manifest.json`, introduced by `6e40a60`. The manifest `key`
  parses as an RSA **public** key with `has_private() == False`. Its derived
  extension ID is independently regression-tested. This is intentional public
  extension identity material, not an API credential or private signing key.
- Provider scan: **148 commits**, 478,939 bytes. Two generic-api-key findings at
  upstream commits `34c2a5e8a2e71d964434962c45c8dbca0ff560e2` and
  `851f786825ac49c269054be3a5c4b5c1f764134c`. Source identifies both as the
  longstanding public YouTube BotGuard request constant, passed to anonymous
  challenge configuration. These are upstream protocol constants, not Morgan
  personal cookies, generated PO tokens or a user's provisioned service key.
  Provider source and pin are unchanged. No raw constant is reproduced here.
- Full staged source export: 2,785,450 bytes before this audit note; one finding,
  the same public manifest key. New source/tests and staged filenames were
  reviewed: only synthetic cookie/session values in tests, no cookie exports,
  Keychain values, environment files, databases, local settings/history, media,
  build/dist outputs, downloaded runtimes or tool binaries staged.
- Historical sensitive-path review found only legitimate source modules named
  `settings.py` / `settings_window.py`, not persisted settings or private files.

These findings require triage; the scanner returns exit **1** when it sees them.
Do not call this a zero-finding scan or suppress arbitrary keys globally. No
personal credential or session material was identified by these checks. This is
evidence from the stated scope, not a guarantee that pattern-based scanning can
detect every possible secret. Any newly discovered real secret stops publication
and requires owner-directed remediation; never rewrite history automatically.

GitHub repository metadata confirmed `MES30004E/mediagrabber` is **Public**.
Recheck it and the target remote before pushing. Re-run history/index checks for
the final commit; verify the remote branch SHA afterward. No force push, merge
to main or release publication is authorized by this audit.

## Accounts observability checkpoint

The subsequent Accounts checkpoint repeated all-local-refs/reflog/history and
provider-history scans: 20 application commits / one public manifest-key finding,
148 provider commits / the same two upstream protocol constants. No new history
finding was identified. The manifest DER was independently parsed as a public
key. Full staged-source export (2,814,798 bytes before this audit wording update)
returned only that same public manifest key; staged filenames contain no private
or generated runtime data. Final commit history is rescanned before pushing.

Accounts tests use synthetic MemoryStore cookies and isolated settings, never a
personal browser/session. The full local suite passed **367 Python tests** and
the extension suite passed **10 tests**. The standalone macOS storage roundtrip
uses its own random synthetic Keychain service/account, with deletion afterward;
it does not read the Companion's stored account. Source changes do not alter the
pinned provider, main or the qualified Swift implementation.

## Playlist workspace checkpoint — 19 October 2026

All-local-ref/reflog scans were repeated before the workspace commit: 21
application commits / the same one public extension-key finding; 148 provider
commits / the same two upstream protocol constants. Only synthetic `.test` media
URLs and controlled thumbnail responses are used by the new regressions. Final
index export and final history are scanned again before publication; any new
credential finding stops the push rather than being silently allowlisted.

The final local suite passed **379 Python tests**, with **10 extension tests**,
protocol drift and dependency checks passing separately. Review caught and
regression tests now cover bounded thumbnail work, same-URL atomic cache writes,
collapsed-restart proportions and normal geometry persistence in fullscreen.
No personal cookies, real private media, build outputs or local preference data
belong in this checkpoint. Per-video media-detail work remains explicitly pending
in `docs/PLAYLIST_WORKSPACE.md`; no release qualification is claimed.

## On-demand inspection checkpoint — 19 October 2026

Pre-commit scans covered 22 application commits plus reflogs/all refs (one known
public manifest-key finding) and 148 provider commits (the same two public
protocol constants). Final index and final commit scans are repeated before push.
New tests use synthetic `.test` metadata and offline yt-dlp processing; no
personal cookies or actual alternate-audio/private-media download is part of
qualification. Inspection summaries exclude raw media/subtitle URLs and headers.

The complete local suite passed **403 Python tests**, plus **10 extension tests**,
protocol drift and dependency checks. All **16 media-detail backend regressions**
also passed with the isolated checksum-verified `2026.10.10.233141` nightly.
Review-driven regressions cover exact-ID selector keywords, yt-dlp's compiled
selector, 403 metadata refresh and stale dialog Apply. This does not claim live
download success, package validation or a release. Main, Swift schema/branches
and provider pin remain unchanged.

## Runtime history/cadence checkpoint — 19 October 2026

Full local verification passed **414 Python tests**, **10 extension tests**,
protocol drift and dependency checks. Read-only review found and then verified
fixes for empty-message timeout backoff and invalid previous-artifact status.
The new ledger is user-local; no runtime metadata or real update error is staged.

Pre-commit all-ref/reflog scans covered 23 application commits (the known public
manifest key) and 148 provider commits (the same two public protocol constants).
Final staged source and the resulting commit history are scanned again before
publication. The full components interface, hosted app packaging and release
updater remain pending as described in `docs/RUNTIME_UPDATES.md`.
