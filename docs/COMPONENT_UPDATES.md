# Updates & Components

Settings → **Updates** brings the existing yt-dlp controls and a background
component inventory together. Opening the page inspects local files/executables;
**Check app/provider releases (media ships with app)** also queries fixed public
GitHub endpoints without a token, cookies, media URLs or account information.

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
old FFmpeg distribution endpoint returned `b6.1.1`. That unrelated distribution
is no longer queried or presented as an update for our own media build. Its
cached records are discarded on load. The app endpoint returned 404 at that
historical check; do not treat this as current release availability.

## Media provenance and release policy

FFmpeg/FFprobe now follow the application release channel, not a third-party
prebuilt-binary feed. Their latest-known field reports the validated app release
tag and explicitly says its media versions are not yet confirmed. It does not
infer that a new app release contains newer FFmpeg, nor offer a downgrade from
the bundled source build to an unrelated distribution. Check time and release
errors are shared with the app record; individual media activation is not offered.

The executable version probe remains separate from `media-build.json` provenance.
A bounded, schema-checked bundled record can display the recorded FFmpeg version
and macOS deployment target only when the inspected executable resolves inside
the bundle. An external executable is not attributed to that record. The card
distinguishes matching, differing and unconfirmed observed versions. A build
record/version match is not proof of binary integrity, current codec behavior,
supported older macOS versions or release/licensing qualification. Missing or
invalid records remain explicitly unavailable, never synthesized from a version
response. Pre-relocation build hashes are not used as installed-binary hashes.

## Installation policy and remaining work

yt-dlp still uses `YtDlpRuntimeManager`: official-channel assets, checksum/archive/
version checks, provider import checks, atomic activation, bundled fallback and
rollback. Manual channel selection does not authorize unattended nightly updates.
Already-dispatched downloads retain their existing runtime snapshot. See
[runtime history/cadence](RUNTIME_UPDATES.md).

Application **stable staging** is now connected separately; see
[app update staging](APP_UPDATES.md). It does not install or replace the app, and
development archives are not accepted as stable updates. Staging success and
time are explicitly distinct from installation/update success.

App/provider/media-tool/Companion replacement is explicitly **Not managed yet**.
This is not a second installer and does not blindly pull the provider submodule.
Qualified release assets, installed-component provenance, package compatibility,
application stop/replacement/recovery and rollback must be connected
before those update actions can be offered. No application release is published
by Check or a development commit. Hosted native-host bundle integration has
passed its narrow protocol checks. Node/provider offline integration now has a
separate hosted gate. Synthetic codec/remux and frozen Cocoa startup gates have
also passed on commit `c8a17c32da90092184ad107d728905b001c1d75e`, run
`39775428272`; these do not establish live downloads or full release qualification.
See [Companion](PACKAGED_COMPANION.md), [provider](PACKAGED_PROVIDER.md),
[media](PACKAGED_MEDIA.md), [GUI](PACKAGED_APP.md) and [replacement](APP_REPLACEMENT.md) scope.
Local licence-gated packaging is not run.
