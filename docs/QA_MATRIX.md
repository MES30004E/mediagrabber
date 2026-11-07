# Product QA matrix

Updated 2026-11-07. Feature statuses/dependencies live in FEATURE_BACKLOG.md.
Evidence below qualifies stated scopes, not entire roadmap features.

| Area / IDs | Verified evidence | Remaining acceptance |
| --- | --- | --- |
| Baseline source | b91faf2145b18d1c0995d369cc945d4b2c186c50; run42383941374 attempt1 success, actual logs/reports inspected | New implementation needs its own reviewed tests and relevant hosted qualification |
| Python / protocol | Hosted Linux1,063passed187.26s/six warnings; macOS backend60passed2.47s; nine protocol fixtures | Live media/account and platform matrix are separate |
| Native UI / U02,U06 | Hosted178passed118.52s; prior e2f72 Cocoa frames across Light/Dark/System and actual900×650,1180×820,1440×900/fullscreen1920×1080; no new visual layout in b91 | History clipping, placeholder/decorative icon contrast, redesign, actualQt6.7, hardware/accessibility certification |
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
Independent review no blocker. Exact380hosted qualification passed;
the table above advances only after subsequent exact-source qualification.
DISPATCH_CAPACITY.md records RED evidence, fixture diagnosis and paired timings.

Restart anchor checkpoint:23RED→56focused0.72s; Cocoa39pass13.86s; full local
1,055pass204.60s/five existing warnings/no skips; independent review no blocker.
JS10/protocol9/pipcheck pass. RESTART_DESTINATIONS.md documents repeated saved-job
and real-dialog coverage, unchanged cleanup scope and deliberate legacy behavior.
Exact-source b91/run42383941374 qualification passed all jobs.

Hidden History checkpoint:6RED/2pass→48focused4.57s; combined native178pass50.97s;
full local1,063pass153.09s/five existing warnings/no skips. Independent review
8pass/no blocker; JS10/protocol9/pipcheck pass. Exact b91hosted qualification passed.
HISTORY_DEFERRAL.md records narrow query/allocation improvements and limitations.

One-shot ownership checkpoint (B4): original8UI cases RED, plus stopped-task
callback failure RED;57focused/23Cocoa lifecycle tests passed. Expanded native
group201passed50.17s and full isolated suite1,074passed150.24s, five existing
deprecation warnings/no skips. Independent review11passed/no blocker; JS10,
protocol9 and pipcheck pass. EPHEMERAL_LIFECYCLE.md documents debugger traceback
roots separately from app ownership. Exact-source hosted qualification pending;
these object-lifetime assertions do not establish total RSS/leak acceptance.

Latest frozen5000 on b91: original max GUI gap1.471686s; extra collection gaps
3.469478/2.425419s; peak423.72MiB; post-removal313.77→351.59MiB. At800,
original max.247639s and collection gaps.448779/.519612s. These include diagnostic
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
