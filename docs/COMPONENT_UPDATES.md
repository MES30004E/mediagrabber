# Updates & Components

Settings → **Updates** brings the existing yt-dlp controls and a background
component inventory together. Opening the page inspects local files/executables;
**Check app/provider/media-tool releases** also queries fixed public GitHub
endpoints without a token, cookies, media URLs or account information.

Each card separates installed/shipped version, latest known version, compatibility
limits, successful-check/update times, last error, rollback and the current update
policy. An executable version response is not a conversion test. A loaded provider
plugin version is not the configured HTTP server's version or proof of token
generation. Accounts retains the separate downloader/provider readiness check.
The shipped Companion manifest is not proof of the version installed in Chrome
or native-host compatibility; use Accounts' setup and connection flow.

## Checks and persistence

The enabled automatic-check preference covers stable yt-dlp and the component
catalog. A running app wakes hourly and checks releases at most daily, with an
hourly backoff for ordinary failed checks. Manual checks bypass those intervals,
but still respect a GitHub retry/rate-limit deadline. Catalog rate limiting pauses
all its GitHub sources and persists across restart. There is no request retry loop.

The catalog keeps private, atomic `runtime/components/releases.json` metadata.
Failures retain the last validated version and successful-check time, while
recording a redacted error. Drafts, prereleases, unexpected release URLs, malformed
tags and oversized responses cannot replace that result. A tokenless 404 is
reported as unconfirmed stable-public-release availability, never 'up to date'.

This uses the official [GitHub release API](https://docs.github.com/en/rest/releases/releases#get-the-latest-release)
and [error/rate-limit guidance](https://docs.github.com/en/rest/using-the-rest-api/troubleshooting-the-rest-api).
API version `2026-03-10` was accepted by the live public endpoints on 19 October
2026. The provider endpoint returned `2.0.2`, while this application's provider
remains pinned at `1.3.1`; it was **not** upgraded or claimed compatible. The
FFmpeg distribution endpoint returned `b6.1.1` (a distribution release tag, not
an inventory probe of the local executable). The app endpoint returned 404.

## Installation policy and remaining work

yt-dlp still uses `YtDlpRuntimeManager`: official-channel assets, checksum/archive/
version checks, provider import checks, atomic activation, bundled fallback and
rollback. Manual channel selection does not authorize unattended nightly updates.
Already-dispatched downloads retain their existing runtime snapshot. See
[runtime history/cadence](RUNTIME_UPDATES.md).

App/provider/media-tool/Companion replacement is explicitly **Not managed yet**.
This is not a second installer and does not blindly pull the provider submodule.
Qualified release assets, installed-component provenance, package compatibility,
application staging/stop/replacement/recovery and rollback must be connected
before those update actions can be offered. No application release is published
by Check or a development commit. Hosted packaging and native-host bundle
integration are still outstanding; local licence-gated packaging is not run.
