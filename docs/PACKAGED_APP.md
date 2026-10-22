# Isolated GUI startup qualification

The existing application entry point accepts an opt-in diagnostic:

```text
Morgan Media Downloader --startup-check /new/report.json
```

Ordinary startup is unchanged. This mode constructs the real MainWindow, waits
for an exposed window, grabs its own rendered contents and closes through the
normal `closeEvent` path. The report must confirm visibility/rendering, the five
existing navigation sections and removal of the running marker after close.
It refuses to overwrite an existing report or follow a final-component symlink.
Exceptions fail the diagnostic and produce bounded, redacted error details.

## Isolation and limits

Before settings/UI imports, the diagnostic creates temporary home/data/log/cache
directories and fresh settings. Authentication, clipboard detection, automatic
Tor, first-run dialogs and updates are disabled. All MainWindow-owned timers are
stopped before entering the event loop, excluding background provider/connection/
clipboard/catalog activity. Existing settings, queue/history, browser profiles,
cookie files, Keychain sessions and managed yt-dlp installs are not used. Source
tests guard against network/Keychain operations and verify existing synthetic
settings remain unchanged. No download or account-verification claim follows.

In frozen mode, ordinary application discovery must locate FFmpeg, FFprobe,
aria2, player-capable Node and the provider server inside the actual app bundle.
This complements the separate executable/version/media/protocol probes; it does
not replace them with synthetic dependency paths.

`scripts/check_packaged_app.py` launches the real GUI executable from a temporary
cwd, with restricted PATH and no inherited Python/Qt/Node/dyld search overrides.
It requires a frozen **Cocoa** report, real render/clean-close evidence and bundled
dependency discovery. A source or offscreen report cannot qualify hosted macOS.
The child is bounded by a 45-second parent timeout and report size is limited.
This uses Qt's own window/render API, not macOS Accessibility or computer control.
No screenshot of the user's desktop or personal application state is taken.

Source/offscreen regression tests prove the diagnostic logic, not frozen Cocoa
execution. Inspect the actual hosted job on the exact commit before claiming the
packaged launch gate passed. This is a narrow startup/render/close smoke test,
not manual interaction coverage or proof of normal background/network behavior.

## Installation and release constraints

The current preferred destination remains `dist/Morgan Media Downloader.app` on
the external project volume. That volume was observed as exFAT; the PyInstaller
bundle depends on symlinks. The user explicitly deferred choosing another
destination. Retain this as an **unresolved requirement**: no automatic move to
Applications, substitute launcher or assumption of exFAT compatibility is allowed.
A later installer must verify its destination can preserve and validate the
bundle before replacement, and fail safely otherwise. No filesystem conversion,
app installation or local Apple build/signing tool is part of these tests.

Hosted success does not publish anything. Supported OS/volume compatibility,
complete corresponding-source/third-party licensing review, the application's
licence choice, explicit release approval, versioned assets/checksums/notes and
safe staged replacement/recovery/rollback remain separate gates. Ad-hoc signature
verification is not Developer ID signing or notarisation.
