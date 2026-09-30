# Codex context — existing Python baseline

Prepared: 1 October 2026. Repository: `MES30004E/mediagrabber`.

## Scope and safety

This is the existing Morgan Media Downloader Python/PySide6 implementation.
Stage 1 prepares its source baseline; it does not start Swift, define a new
Swift architecture, or introduce migration CI. Preserve the Python app as the
behavioural reference. Do not delete it or rewrite yt-dlp extraction.

Read `README.md`, `ARCHITECTURE.md`, `docs/CURRENT_ARCHITECTURE.md`, and
`docs/SWIFT_MIGRATION_NOTES.md` before later work. Check the actual commit,
working tree, submodule state, and tests; this document is not a live status API.

The owner's local Mac has no admin access and cannot accept the Xcode licence.
Never require local Xcode, xcodebuild, xcrun, sudo, or licence acceptance.
Source development is not blocked by that constraint. Codex Cloud is not
assumed to be macOS; future native validation belongs on an authorised hosted
macOS runner, not this local Mac. No such workflow is implemented in Stage 1.

The initial source must not be pushed to a Public repository without explicit
approval. Verify Private visibility before publishing; never force-push to
replace unexpected remote history. No app-level licence is selected yet.

## Source/dependency layout

- `src/morgan_media_downloader/`: application code; retain this layout.
- `tests/`: deterministic Python, offscreen Qt, and local media integration tests.
- `launcher.py`, `pyproject.toml`, `requirements.txt`: entry/package/dependencies.
- `build_macos.sh`, `MorganMediaDownloader.spec`, `scripts/`: existing packaging.
- `resources/`: source icon assets; generated media binaries are ignored.
- `resources/bin/ARIA2_PROVENANCE.md`: retained native aria2 provenance, not its binary.
- `bgutil-ytdlp-pot-provider/`: explained/pinned upstream submodule, not vendored caches.

Provider URL: `https://github.com/Brainicism/bgutil-ytdlp-pot-provider.git`.
Provider commit: `7608dd51ee813b48cf9a6d68c6e42cb197ce10e0` (1.3.1).
Use `git submodule update --init --recursive` after cloning. Do not reset or
rewrite the upstream provider to hide local metadata differences. The original
external-volume checkout had mode-only modifications and untracked Finder
metadata; those are not application changes or new provider code.

## Stage 1 changes

- Stronger `.gitignore` excludes credentials, browser exports, runtime state,
  local tooling, caches, build outputs, media, partials, and Finder sidecars.
- `:ytwatchlater` reaches yt-dlp unchanged instead of becoming a search.
- Explicit Watch Later playlist/feed URLs normalise to the canonical WL URL.
- Ordinary text searches, other playlists, and existing auth policy remain intact.
- Default Tor Browser discovery uses user Applications then system Applications;
  saved locations remain configurable and are not overridden.
- Python bootstrap no longer deliberately puts the base interpreter in temporary storage.
- Documentation no longer claims implemented previews/NEWNYM are missing.

## Environment and verification

The previous `.venv` referenced a reclaimed `/private/tmp` Python installation.
Stage 1 preserved it as an ignored backup and recreated `.venv` using the
already installed user-local uv-managed Python 3.12.13, with `venv --copies`.
An attempted project-local uv interpreter install failed because the external
exFAT volume cannot host its symlinks. Store base Python durably on a symlink-
capable user filesystem; copy-based venvs can live on the external project disk.
No administrator access or compiler was required. Do not copy the local venv to Cloud.

On a fresh symlink-capable environment, use uv-managed Python and install
`requirements.txt` into an isolated venv. On exFAT use the copy-based bootstrap
in README. Wheels-only installation avoids attempting native dependency builds.
The package is under `src`; pytest config supplies that import path. Source-mode
launch needs `PYTHONPATH=src` unless the package has been installed separately.

Test command used (with fresh temporary state each run):

```sh
stage1_test_root=$(mktemp -d /private/tmp/morgan-stage1-tests.XXXXXX)
PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen \
MORGAN_DATA_DIR="$stage1_test_root/data" \
MORGAN_LOG_DIR="$stage1_test_root/logs" \
MORGAN_CACHE_DIR="$stage1_test_root/cache" \
.venv/bin/python -B -m pytest -p no:cacheprovider
```

Fresh local result on 1 October 2026: **222 passed** on Python 3.12.13,
pytest 8.4.2, yt-dlp 2026.08.19, PySide6 6.11.2. New targeted tests were first
observed failing against the old implementation (11 failed, 58 passed), then
the complete suite passed after the fixes. `pip check` found no broken requirements.
No current package build, live private YouTube download, cookie extraction,
Tor session, or live torrent swarm was validated. Dependency ranges remain unpinned.

Media tests generate tiny fixtures with executable ffmpeg/ffprobe under
`resources/bin`. The existing copies are arm64 macOS binaries and are not in
Git. Provision platform-appropriate trusted tools for a fresh Linux/macOS test
environment; do not execute Mach-O binaries in a Linux Cloud environment or
silently call unavailable-tool tests a complete pass. Torrent unit tests mock
external transfers. The normal build downloads ffmpeg/ffprobe but not aria2c.

## Privacy boundaries

Never commit cookies, browser auth exports, Keychain values, personal cookie
paths, `.env`, private keys, downloaded media, local settings/history, SQLite
files, logs, or caches. Data normally lives in user Library directories and
user-selected download folders; keep it there. `.gitignore` does not sanitize
source strings or tracked files. Review staged names and contents before commits.

Do not use private accounts for automated CI. Authentication tests use fixtures.
Keep diagnostics redacted and avoid uploading local histories or browser profiles.

## Known follow-up work (not silently fixed in Stage 1)

- Live Watch Later/private-playlist access depends on authorised cookies; Auto's
  error-substring detector may miss the site's actual response. Explicit cookie
  modes remain available. Auto login test checks public extraction, not login.
- Settings login test only routes through Managed Tor, not other selected proxies.
- Direct Download of a Spotify input can enqueue multiple match candidates;
  use Analyse and explicit selection pending a dedicated review.
- Converter cancellation, stderr pipe draining, and overwrite confirmation need review.
- Torrent blocking stdout reads can delay cancellation; combined previews for
  multiple torrents need dedicated validation.
- Advanced safe-options/Console-detail values are stored but not applied.
- Existing automatic Managed Tor circuit retries need a separate policy review;
  do not expand identity-changing retries as a bypass mechanism.
- Fresh-clone aria2 acquisition, dependency pinning, checksums, licensing,
  signing/notarisation, and universal packaging remain follow-up work.

## Next Cloud task

Only after a private pushed baseline is confirmed: inspect these documents,
current source/tests/submodule, and establish the Cloud test prerequisites.
Then obtain explicit authorization for migration design. Stage 1 does not
authorize a Swift implementation or local Xcode commands.
