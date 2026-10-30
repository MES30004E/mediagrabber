# Tokenless App Update Staging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Updates to tokenless, integrity/compatibility-checked staging of a newer stable app release while never replacing the running installation.

**Architecture:** Keep `YtDlpRuntimeManager` unchanged. A new app-specific stager consumes the fixed repository's public latest-release metadata, validates exact asset URLs/digests, stages through the shared archive validator, and persists a private staging ledger. The existing Settings task manager owns download/cancel/status callbacks.

**Tech Stack:** Existing Python/PySide6, urllib, hashlib, shared app archive/signature validation, pytest/offscreen Qt.

**Spec:** User's Reliable Downloads, Better UX and Public Releases brief, priorities 4–5; `docs/DEVELOPMENT_ARCHIVES.md`, `docs/APP_REPLACEMENT.md`; official GitHub release-asset metadata reference.

## Global Constraints

- No local Xcode/xcodebuild/xcrun/sudo/Homebrew/signing builds, personal cookies or live private-media tests.
- Stay in the existing development checkout; preserve main/Swift/provider pin and unrelated drafts.
- No release/tag/asset publication, automatic application activation, filesystem conversion, installation or fallback destination.
- Only fixed public repository endpoints and HTTPS GitHub asset/CDN redirects; never send cookies or GitHub tokens.
- Development candidates remain rejected by stable staging. Newer stable version, arm64 macOS compatibility, exact size/digests, archive/bundle identity and signature checks precede successful staging.
- Failures/cancellation preserve the running installation and any previously staged candidate. A stage is not an installation, publisher signing/notarisation or live-download qualification.

## Review Focus

- Wrong repository/tag/redirect, missing/duplicate digest metadata and development manifests must fail closed.
- Downgrades, unsupported platform/minimum OS and version mismatches must not become staged success.
- Interrupted/corrupt/oversized downloads and concurrent stage requests must not activate or discard the previous candidate.
- Cancellation, rate limits and restart must retain truthful state without exposing credentials in errors.
- UI staging must run in the existing worker lifecycle, not Apply unrelated settings, install anything or report last-stage time as last-install time.

### Task 1: Shared archive policy and app stager

**Files:** Modify `app_archives.py`; create `app_updates.py`, `tests/test_app_updates.py`; extend archive policy tests.

**Interfaces:** Keep `extract_development_archive` strict. Add `extract_release_archive(archive, manifest, destination, *, validator)` for stable metadata. `AppUpdateManager(root, installed_version, *, fetcher, downloader, validator, platform_info)` exposes `stage_latest(cancel, progress)` and `describe()`.

- [ ] Write failing tests for stable/development separation, real synthetic archive staging, metadata/digest/version/platform rejection, cancellation/failure preserving previous stage, restart and rate-limit backoff.
- [ ] Implement streamed bounded private staging, exact metadata validation and stable extraction using the existing archive implementation. No installation API is invoked.
- [ ] Run full isolated Python suite and relevant JS/drift checks.

### Task 2: Updates UI integration

**Files:** Modify `settings_window.py`; create `tests/test_app_updates_ui.py`, `docs/APP_UPDATES.md`.

**Interfaces:** Optional injected `app_update_manager`; worker kind `app-update`; stage/cancel buttons and separate last-stage/status/error text. Buttons recover on finish; cancellation uses existing task-manager ownership.

- [ ] Write failing UI tests proving background execution, no Apply/install side effect, progress/result/error/cancel/restart wording and usable narrow layout.
- [ ] Implement the connected UI, document stable asset contract and explicitly unfinished activation/recovery/release gates.
- [ ] Full-suite verification, one focused read-only review and regression fixes; audit app/provider history plus exact staged index before commit/push. Do not cancel the live archive qualification run with a push.
- [ ] Inspect actual hosted results on the new commit before claiming qualification.
