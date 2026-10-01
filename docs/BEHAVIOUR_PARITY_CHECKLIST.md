# Behavior parity checklist — design baseline

Reference: `6a024ec97d2521beed1c6cce2752aaa605425390`. A classification is a
requirement decision for review, not a claim that Swift currently implements it.
Source paths are relative to `src/morgan_media_downloader/`; tests to `tests/`.
All existing Python code remains the executable comparison baseline.

| Area | Behavior | Classification | Source / existing evidence | Native acceptance evidence required |
| --- | --- | --- | --- | --- |
| Input parsing | Multiline classification, URLs versus text searches, sanitation | Preserve | parsing.py; test_parsing.py | Shared fixtures with identical targets/order |
| YouTube | Exact :ytwatchlater; canonical feed/WL aliases; ordinary playlist/watch URLs unchanged | Preserve | parsing.py; test_parsing.py, test_auth.py | Exact target and authenticated-boundary fixtures |
| YouTube | One transfer 403 metadata refresh and new playable format resolution | Preserve | downloader.py; test_downloader_diagnostics.py | Failed initial metadata/transfer fixture, exactly one refresh |
| Authentication | Public-first Auto; supported browser/cookiefile options; private failures never drop auth | Preserve | auth.py, downloader.py; test_auth.py, test_downloader_policy.py | Same attempts, effective mode and safe errors |
| Authentication | Reset absent browser profile to empty; yt-dlp receives None | Preserve | auth.py, settings_window.py; test_settings_window.py | Empty home test with no fake browser installation |
| Authentication | macOS Chromium-family friendly profile discovery | Preserve | auth.py; test_auth.py | Metadata fixtures; authorized macOS cookie access tested separately |
| Authentication | Auto message-substring entitlement inference; public login check misread as account verification | Review before preserving | auth.py; test_auth.py | Product copy and error taxonomy review; no inferred access claims |
| Playlists | Expand nonempty entries; preserve collection titles/indexes/original source | Preserve | downloader.py; test_auth.py, test_playlist_progress.py | Multi-item snapshot fixtures and cancellation |
| Preview | Select/all/none/invert, confidence and subtitle choices, cancellable analysis | Preserve | ui.py, models.py; test_ui_lifecycle.py; UI paths | Native selection/analysis tests including late callbacks |
| Download | Direct Download performs internal analysis; multiline tasks independent | Preserve | ui.py _start_analysis/_enqueue_payload | Command and ordering tests; scoped collection selections |
| Formats | Concrete playable IDs, compatible codecs and quality fallback warnings | Preserve | formats.py, downloader.py; test_formats.py, test_downloader_policy.py | Identical format cases and warning persistence |
| Progress | Bytes/speed/ETA/fragments, stages and unknown totals; no premature Downloading | Preserve | downloader.py, ui.py; test_job_watchdog.py, test_playlist_progress.py | Hook-to-event fixtures, stale attempt rejection |
| Queue | Media/Torrents/All, stable ID selections/details during refresh; configurable concurrency | Preserve | ui.py, models.py; test_ui_diagnostics.py, test_ui_lifecycle.py | Native ID-based selection and dispatcher limits |
| History | Search/status filters on same SQLite jobs, persisted warnings and verification | Preserve | database.py; test_database.py, test_job_diagnostics.py | Legacy payload and native history fixtures |
| Persistence | WAL jobs, forward-compatible fields, atomic settings/schema migration/corrupt recovery | Preserve | database.py, settings.py; test_database.py, test_settings.py | One-writer/crash tests, backup/rollback compatibility |
| Restart/recovery | Active jobs restore Interrupted; owned threads/tasks drain at shutdown | Preserve | database.py, tasks.py, ui.py; test_tasks.py, test_ui_lifecycle.py | Worker crash/reconnect; no automatic replay |
| Restart/recovery | Resume/Retry keep partials; Restart waits and resets only recorded state | Preserve | file_ownership.py, ui.py; test_file_ownership.py | Attempt fencing, confirm replace/keep and resume fixtures |
| File ownership | Exact inventories and selected-root confinement; unrelated folders retained | Preserve | file_ownership.py; test_file_ownership.py | Native grants, symlink/out-of-root and race tests |
| File ownership | Trash fallback may permanently unlink completed files after failed Trash move | Review before preserving | file_ownership.py delete_owned_files | Explicit user policy and native Trash-error tests |
| Compatibility/remux/transcode | QuickTime/Universal MP4 baseline, fast-start, stream copying and selective conversion | Preserve | compatibility.py; test_compatibility.py, test_local_converter.py | Tiny local-media fixtures plus hosted macOS playback QA |
| Conversion | Five profiles, container constraints, quality/resolution, no upscale by default | Preserve | local_converter.py; test_general_converter.py | Same conversion plans, output codec/container verification |
| Conversion | Cancellation absent; serial stderr read risks blocking; overwrite consent gap | Known defect / do not copy blindly | local_converter.py, ui.py; documented limitations | Separate engine fix and cancellation/drain/overwrite regression tests |
| Subtitles | Atomic mux, language/codec verification, optional failure preserves playable output | Preserve | subtitle_mux.py; test_subtitle_mux.py, test_downloader_diagnostics.py | Exact media retention and completed-warning tests |
| Metadata/artwork/chapters | Preserve requested metadata, artwork disposition and chapters, verify outputs | Preserve | media_verification.py, local_converter.py; test_media_verification.py, test_general_converter.py | ffprobe and Mutagen fixtures, no unintended streams |
| Runtime updates | Official source, SHA256/version/structure, provider compatibility, snapshots, rollback/bundled fallback | Preserve | yt_runtime.py; test_yt_runtime.py | Verified update fixtures; active attempts retain captured version |
| Runtime updates | Dynamic downloaded Python code in distributed signed native app | Review before preserving | yt_runtime.py, build_macos.sh | Distribution/hardened-runtime decision, signed bundle tests |
| PO token provider | Upstream pinned plugin; HTTP-first and script fallback; selected proxy forwarding | Preserve | provider.py, downloader.py; provider submodule; test_auth.py | Plugin import tests and controlled provider protocol test |
| PO token provider | Source-folder/runtime discovery can report available without compiled generation proof | Known defect / do not copy blindly | provider.py _valid_script_home/check_provider | Readiness distinguishes source discovered from verified generation |
| Proxy | Direct/System uses system routing; HTTP/SOCKS and Tor socks5h, remote DNS | Preserve | network.py; test_network.py | Per-operation routing fixtures and credential redaction |
| Proxy | Login test forwards only Managed Tor proxy; updater/probes use separate routes | Known defect / do not copy blindly | settings_window.py, provider.py, yt_runtime.py | One declared routing scope per operation; no all-traffic Tor claim |
| Managed Tor | Owned executable/data, dynamic ports, cookie auth, stale ownership checks, bounded launch collision retry | Preserve | managed_tor.py; test_managed_tor.py, test_tor_health.py | Host lifecycle/control fixtures; never stop foreign Tor |
| Managed Tor | Automatic target-triggered circuit rotation/retry; manual NEWNYM cooldown | Review before preserving | downloader.py, managed_tor.py; test_tor_retry.py | Explicit policy decision; no expanded identity-changing loops |
| External Tor | Discover 9150 then 9050, status probes, no process ownership | Preserve | network.py, ui.py; test_network.py, test_tor_health.py | No start/stop or browser-profile modification |
| Torrents | Torrent/magnet metadata/file selection, Direct/System only, private discovery restrictions | Preserve | torrent.py; test_torrent.py | Fixture metadata/argv/selection tests; no live swarm required |
| Torrents | CN/SD counters, partial inventory and seeding state | Preserve | torrent.py; test_torrent.py | Adapter events show connected peers/seeds, not tracker estimates |
| Torrents | Blocking readline can delay cancellation | Known defect / do not copy blindly | torrent.py download_torrent | Independent cancellation timer and quiet-child regression |
| Spotify | Public oEmbed → ranked artist/title YouTube candidates; explicit preview choice | Preserve | spotify.py, downloader.py; test_spotify.py | Rank/selection fixtures; no Spotify stream extraction |
| Spotify | Direct Download can enqueue all candidate matches | Known defect / do not copy blindly | ui.py _analysis_ready; README known limitations | Explicit candidate choice before native enqueue |
| Spotify | Full authenticated album/playlist expansion | Future enhancement | spotify.py; README | Separate official API/credential design; no scraping fallback |
| Console/logging | Bounded 10,000 entries, job/source/level filters, rotating redacted logs | Preserve | console.py, logging_setup.py; test_console.py, test_security.py | Structured IPC allowlists, secret-bearing strings and export tests |
| Settings | Working-copy Apply/OK/Cancel; atomic settings; main selector consistency | Preserve | settings.py, settings_window.py, ui.py; test_settings.py, test_settings_window.py | Native editor persistence and cancellation tests |
| Settings | Stored advanced safe-options/Console detail fields not operationally applied | Known defect / do not copy blindly | settings.py, ui.py; README | Omit or explain unavailable controls until implemented |
| Finder | Open/reveal recorded output; safe native file dialogs/Trash | Preserve | ui.py open_selected/reveal_selected; paths.py | Hosted AppKit tests plus manual macOS QA (not covered by Linux suite) |
| Security/privacy | No shell=True, no DRM/account bypass, headers absent from history, Keychain proxy passwords | Preserve | keychain.py, models.py, logging_setup.py; test_security.py, test_thumbnail_cache.py | Native Security fixtures, private IPC and redacted persistence tests |
| Packaging | Native engine acquisition/provenance, app license, architecture builds, signing/notarisation | Review before preserving | build_macos.sh, spec, resources/bin/ARIA2_PROVENANCE.md | Release manifests/checksums/licenses and separate hosted builds |

“Preserve” freezes intended externally visible contracts, not every internal
implementation or known defect. Existing automated tests mock private/network
operations; they do not prove live entitlement, browser permissions, playback,
Tor anonymity, VPN activation or torrent swarm availability. Review items need
recorded decisions before they can become native acceptance criteria.
