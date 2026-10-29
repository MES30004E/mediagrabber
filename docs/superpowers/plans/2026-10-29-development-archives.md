# Development App Archives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce and exercise a versioned development archive/manifest/checksum/notes contract inside hosted CI, without publishing or installing anything for the user.

**Architecture:** Extend the existing hosted actual-bundle qualification. A stdlib module creates an archive from a verified Apple Silicon app and safely stages an integrity-checked extraction; a hosted-only script launches that extracted copy through the existing isolated Cocoa probe.

**Tech Stack:** Existing Python 3.12, tarfile, hashlib, plistlib, pytest and hosted macOS validation.

**Spec:** The user's Reliable Downloads, Better UX and Public Releases brief, priority 5; existing `docs/PACKAGED_APP.md` and `docs/APP_REPLACEMENT.md` constraints.

## Global Constraints

- No local Xcode, xcodebuild, xcrun, sudo, Homebrew, PyInstaller or signing builds.
- No live accounts, personal media, local installations, fallback destination or new launchers.
- No upload, tag or release; development metadata always has `publication_approved: false`.
- Preserve main, qualified Swift branches, provider pin and unrelated draft plans.
- Existing destinations must not be overwritten. Failed staging must not affect a working app.
- SHA-256 integrity is not publisher authentication, notarisation or licence clearance.

## Review Focus

- Tar traversal and symlink escapes must fail before a candidate can be used.
- Tampered/truncated archives must fail integrity checks before extraction.
- An archive version or architecture must match its actual bundle, not only its filename.
- Missing/invalid candidate metadata must fail closed, not become a stable release.
- Native verification is hosted-only; source fixtures must not execute Apple tools.

### Task 1: Versioned development archive contract

**Files:** Create `src/morgan_media_downloader/app_archives.py`, `tests/test_app_archives.py`, `docs/DEVELOPMENT_ARCHIVES.md`.

**Interfaces:** `build_development_archive(app, destination, version, commit, *, validator)` returns a manifest; `extract_development_archive(archive, manifest, destination, *, validator)` returns the extracted app. Default validation reuses the existing bundle identity/signature check. Tests inject fixture validation only.

- [x] Write fixtures for an arm64 Mach-O header, expected Info.plist identity/version and a relative framework-style symlink.
- [x] Observe failing tests for build/round-trip, mismatch/overwrite refusal, invalid development metadata, corruption, traversal, symlink escape, special entries and extraction bounds.
- [x] Implement bounded manifest validation, SHA-256/size checks, safe tar handling and new-destination staging. Always emit development-only metadata, checksum file and notes.
- [x] Run targeted and full isolated Python suites, JS tests and protocol drift check.
- [x] Obtain focused read-only review; fix Important issues before commit.

### Task 2: Hosted actual archive round-trip

**Files:** Create `scripts/check_packaged_archive.py`; modify `.github/workflows/migration-validation.yml`.

**Interfaces:** Hosted-only CLI consumes the already-qualified actual bundle and the exact `GITHUB_SHA`; uses Task 1 and existing isolated Cocoa launch validation on the extracted copy.

- [x] Add fixture-boundary tests for the probe's source preservation and failed-launch propagation.
- [x] Add the probe after existing native/provider/media/GUI/replacement gates. Keep all candidate files in runner-owned temporary storage.
- [ ] Review/stage only this checkpoint, scan all app/provider refs and the exact staged index, verify public visibility, then commit/push development only after the current CI run ends.
- [ ] Inspect the exact new hosted run and actual logs before claiming archive qualification.

## Explicit remaining work

This does not implement a stable-release promotion workflow, artifact upload, publisher signing/notarisation, source-offer/licensing clearance, tokenless app asset download, post-exit updater coordination, crash journal or rollback UI. Those remain part of the overall goal; this contract must not be described as the complete updater.
