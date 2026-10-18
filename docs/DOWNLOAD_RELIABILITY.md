# Authenticated YouTube reliability checkpoint — 18 October 2026

This is the first checkpoint of the Reliable Downloads / Better UX / Public
Releases request. It implements download/runtime corrections, not the complete
playlist redesign, component dashboard or public release pipeline.

## Evidence and cause

The reported per-video failure is `The page needs to be reloaded.` after a
successful 828-item Watch Later expansion. Flat playlist analysis does not run
the same player extraction as an individual download and cannot prove readiness.

The official [upstream issue 17389](https://github.com/yt-dlp/yt-dlp/issues/17389)
records the same authenticated `tv_downgraded` failure. Upstream
[PR 17723](https://github.com/yt-dlp/yt-dlp/pull/17723) adds `tv_samsung`;
[PR 17805](https://github.com/yt-dlp/yt-dlp/pull/17805), merged 10 October 2026,
makes it a default for authenticated and unauthenticated extraction and removes
the broken made-for-kids fallback. Its merge commit is
`897341241f2bfb2439fe0367f4c7c9ccd29a3828`.

Official release metadata observed on 18 October:

- Stable remains `2026.08.19`, with `tv_downgraded` in authenticated/premium defaults.
- Nightly `2026.10.10.233141` is generated from the merge commit above; inspected
  authenticated defaults are `web_embedded`, `tv_samsung`, `web` and premium
  defaults are `web_creator`, `tv_samsung`, `web`.
- The nightly Unix zipapp SHA256 is
  `f40b6a9e4c5786360953911cab5d2f87507626b8fb7bfee3f8f1c2e5cf341fae`, verified
  against its official `SHA2-256SUMS` before import.

This is a strongly matching upstream cause, not a reproduction against the
user's account. No personal cookie or live YouTube request was used by this work.

## Implemented behavior

- The existing `YtDlpRuntimeManager` supports an explicit official nightly
  channel, with exact repository/tag/asset binding, checksum/zip/version checks,
  provider import compatibility, persistent selection and rollback. Stable
  automatic checks remain stable-only; selecting the manual nightly channel does
  not opt into unattended nightly updates.
- Settings → Advanced offers a manual channel selector alongside the existing
  Check Now / Update Now / Roll Back / Use Bundled Version controls. Active
  channel, latest nightly and last error are displayed. These are import and
  integrity checks, not a live download-success indicator.
- Rejected candidate metadata is kept separately from the last successful
  current/previous runtime and successful-update time. A failed activation also
  preserves an explicit Use Bundled selection.
- Explicit authentication is no longer automatically discarded after a format
  error, during either analysis or downloads. User-requested unauthenticated
  retry remains a separate explicit action. Auto's ordinary public-first policy
  and known-Watch-Later upfront authentication remain unchanged.
- Player reload failures and PO-token-provider failures have separate categories
  and recovery instructions. A failed per-video attempt clears stale metadata
  success/format counts; a failed refresh after HTTP 403 reports Metadata refresh,
  not successful metadata or a transfer-stage error. The existing single media
  403 refresh bound remains in place.
- Existing Node/Deno discovery now explicitly supplies `js_runtimes` to yt-dlp
  for analysis, download and optional subtitle requests. Provider generation and
  player-JavaScript solving have different minima: preserve provider Node20+ /
  Deno2+, require player Node22+ / Deno2.3+. A provider-compatible but too-old Node
  must not hide a valid Deno/newer Node. Deno's named version output is parsed
  correctly. yt-dlp still validates its own runtime and solver requirements.

No extractor internals were patched, no forced alternate-player workaround was
added, and no global dependency downgrade or replacement of the stable venv was
performed.

## Isolated native-runtime qualification

The real manager was exercised under a fresh temporary root, not the normal
application-support runtime. Stable `2026.08.19` was downloaded/verified and
activated there, followed by the official nightly. The pinned bgutil plugin
`7608dd51ee813b48cf9a6d68c6e42cb197ce10e0` (1.3.1) imported successfully against
both runtimes. The nightly's JS director reported Node available using the
discovered Node24 executable. Rollback restored stable successfully. This proves
import/solver availability, not token generation, account entitlement, media
transfer or format availability for a particular video.

The original venv and normal user runtime were not changed. The qualified
temporary artifacts are not release assets and must not be committed.

## Live validation — user participation required

1. Start the existing source application from the repository root:

   ```sh
   PYTHONPATH=src .venv/bin/python -m morgan_media_downloader
   ```

2. In Settings → Advanced, choose **Nightly** as the manual update channel, click
   **Check Now**, review the version, then **Update Now**. These are immediate
   component actions, not unsaved settings edits; no extra Apply is needed for a
   runtime action. Do not infer account verification from update success.
3. In Accounts, select/verify the already captured **YouTube Companion** session
   and Apply if manually changing its authentication method. A new successful
   Companion capture now activates that method automatically, without saving
   unrelated pending settings. Verify Session and Check downloader/provider
   remain separate checks; neither is a successful individual download.
4. Explicitly retry one authorized video, initially the reported failing test
   video if appropriate. Check the active runtime version, failure stage,
   authentication and playable-format count in Details. Separately verify the
   provider's actual readiness and the output's playback.
5. If the candidate regresses behavior, use **Roll Back** (previous verified
   runtime) or **Use Bundled Version**. Already-dispatched attempts retain their
   existing snapshot; stop/retry deliberately rather than assuming a mid-transfer
   runtime change.

No automatic live validation is performed. A browser-playable video is evidence
of browser access, not proof that a particular yt-dlp player/client will succeed.

## Automated verification and publication gate

```sh
test_root=$(mktemp -d /private/tmp/morgan-reliability-tests.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
MORGAN_DATA_DIR="$test_root/data" MORGAN_LOG_DIR="$test_root/logs" \
MORGAN_CACHE_DIR="$test_root/cache" \
.venv/bin/python -B -m pytest -q -p no:cacheprovider
node --test companion/tests/core.test.mjs
.venv/bin/python scripts/check_backend_protocol.py
.venv/bin/python -m pip check
```

On macOS, the full suite's uniquely named synthetic Keychain round-trip requires
ordinary user Keychain access; a restrictive execution sandbox returns OSStatus
100001. Grant that narrowly scoped test access instead of skipping it. No real
browser cookies or account are used in the automated suite.

Before any push, independently scan all local refs/reflogs/history and staged
source, including the provider's nested local history. Keep redacted reports in
ignored local tooling, review every finding and stop on real secrets. The public
Chrome extension identity key is intentional public material, not a private
signing key; upstream anonymous BotGuard request constants likewise require
explicit source-based triage rather than treating all high-entropy strings as
Morgan account credentials. Never add a broad allowlist for arbitrary keys.

The repository was verified Public through GitHub metadata. Public release
publication still requires separate approval, complete hosted qualification,
packaging checks and checksums. This checkpoint does not claim a built .app,
signing/notarization, hosted CI success or completion of the remaining priorities.
