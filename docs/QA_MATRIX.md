# Product QA matrix

Updated 2026-11-07. Feature statuses/dependencies live in FEATURE_BACKLOG.md.
Evidence below qualifies stated scopes, not entire roadmap features.

| Area / IDs | Verified evidence | Remaining acceptance |
| --- | --- | --- |
| Baseline source | e2f3ea33009610ae6bcf26dd06686ed33a539f33; run42378146636 attempt2 success, actual logs inspected | New implementation needs its own reviewed tests and relevant hosted qualification |
| Python / protocol | Local1,017passed164.28s; hosted Linux1,017passed332.82s; macOS backend60; nine protocol fixtures | Live media/account and platform matrix are separate |
| Native UI / U02,U06 | Hosted92passed54.48s; local92passed34.19s;72 Cocoa frames across Light/Dark/System and actual900×650,1180×820,1440×900/fullscreen1920×1080 | History clipping, placeholder/decorative icon contrast, redesign, actualQt6.7, hardware/accessibility certification |
| Swift preserved | Hosted build and25tests, including two actual Python worker tests | No new Swift work authorized |
| Companion / AU01–AU02 | JS10/no skips; frozen native protocol5cases; extension identity retained | Manual browser Incognito, consent/Keychain/readiness and real authorized transfer |
| Bundled tools / R03 | Provider1.3.1, Nodev24.22.0/Canvas PNG; nine synthetic offline media cases; Cocoa launch/clean shutdown | Real token generation, live downloads/torrents, supported OS/codec matrix |
| Queue / Q01–Q07,Q09,Q11 | Frozen100/800/1000/5000×2,18stages each; strict report validation; real track/label pixels; two owned workers, final0; independent SQL; bounded restart/clear | Long-run retention, production timer cost, remaining GUI gaps, process relaunch/live transfers/real Trash/cross-volume races |
| Archive / R04,R06 | Strict signatures, exact contents/symlinks/modes, extracted launch, retained backup, source unchanged | User installation/exFAT, durable updater recovery, Developer ID/notarisation |
| Library / V01–V02 | No implemented playback accepted | Real local playback/track/seek/volume/fallback and packaged codec QA |
| Auth/privacy / D01–D03,M02–M04,F01 | Deterministic policy/routing/storage tests only for their documented contracts | Site-scoped lifetimes/onboarding and user-participating private-site/Tor acceptance |

## Performance baseline, not a release pass

New scheduler checkpoint: focused72pass14.42s, Cocoa13pass3.03s and full local
1,030pass169.54s/5knownwarnings/no skips; JS10/protocol9/pipcheck pass.
Independent review no blocker. Hosted qualification for this source is pending;
the table above intentionally remains pinned to the last qualified e2f baseline.
DISPATCH_CAPACITY.md records RED evidence, fixture diagnosis and paired timings.

Latest frozen5000: original max GUI gap1.032948s; extra collection gaps
2.429543/2.472245s; peak456.05MiB; post-removal355.08→384.06MiB. At800,
original max.209707s and collection gaps.496925/.340003s. These include diagnostic
verification costs and are not controlled paired improvements or proof of leaks.
Keep the independent90s original/collection diagnostic budgets and all safety
assertions. Longitudinal profiling and real production timers remain P0 work.

## Repeatable local checks

Use the repaired project `.venv`, isolated MORGAN_DATA_DIR/MORGAN_LOG_DIR/
MORGAN_CACHE_DIR and `PYTHONDONTWRITEBYTECODE=1`.

```sh
QT_QPA_PLATFORM=offscreen .venv/bin/python -B -m pytest -q -p no:cacheprovider
node --test companion/tests/core.test.mjs
.venv/bin/python -B scripts/check_backend_protocol.py
.venv/bin/python -B -m pip check
```

Own-window Cocoa tests use `QT_QPA_PLATFORM=cocoa`; no Accessibility automation
or personal data. Build/sign/archive checks run only on hosted macOS. New tests
must fail for their confirmed defect before the fix; timing observations do not
replace deterministic complexity/ownership/persistence assertions.
