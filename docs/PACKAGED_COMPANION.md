# Self-contained Companion host

The PyInstaller spec now includes the extension assets and a separate console
`MorganNativeHost` executable inside `Morgan Media Downloader.app/Contents/MacOS`.
The ordinary app remains a windowed Qt executable and is explicitly named as
`CFBundleExecutable`. The helper embeds Python/stdlib code independently and does
not start Qt or import yt-dlp. Its one-file bootloader may extract runtime files
to a temporary directory; cookie data is never part of those files.

In frozen mode, Accounts → Connect validates the sibling helper and shipped
extension files before changing registration. The private user-level host wrapper
executes that helper with a fresh PyInstaller environment, not a checkout path,
venv or external Python. The existing fixed origin, framing limits, consent/
nonce/single-use rules and Keychain storage remain unchanged. Chrome installation
and Allow in Incognito are still manual. Setup instructions use the bundle's
extension directory rather than a source-relative path.

Source setup remains available. It registers a Python bootstrap, but creating a
legacy Desktop launcher now requires `--development-launcher`. Frozen setup
never creates or removes that launcher. Switching a recognized source host to a
validated frozen host removes only its owned obsolete bootstrap. Moving an app
after registration requires Connect/Reconnect to update its absolute wrapper
path. The old ownership marker is retained for backward-compatible inspection;
it does not indicate that frozen mode uses a development launcher.

## Qualification

The hosted **Packaged runtime integration (not release qualification)** job runs after the
full Linux Python/extension suite and macOS backend/Swift checks. It invokes the
existing spec directly, in runner-temporary build/output folders; it does not run
the local replacement script or install an app on the developer's Mac.

`scripts/check_packaged_companion.py` checks GUI bundle identity, an arm64 Mach-O
helper, shipped extension identity/assets and five real helper subprocess cases:
ping, wrong origin, oversize length, truncated frame and duplicate JSON keys.
It changes cwd, removes Python import environment variables and restricts PATH,
requires exactly one framed response and no stderr, and never transfers cookies
or reads/writes a Keychain item. Hosted `codesign --verify --deep --strict` checks
the resulting ad-hoc-signed bundle; this is not Developer ID signing/notarization.

The design follows the official [PyInstaller spec/bundle documentation](https://pyinstaller.org/en/stable/spec-files.html).
Do not run PyInstaller, Apple licence-gated tools or local signing as part of this
qualification: packaging is hosted. Source tests alone do not prove a frozen
helper runs; inspect the actual hosted job before declaring that result.

## Still not a release

This job does not upload, publish, tag, replace an installed app, or qualify
live Chrome/Keychain interaction or authenticated downloads. GUI launch has a
separate [isolated Cocoa gate](PACKAGED_APP.md).
The additional offline provider checks are described in [PACKAGED_PROVIDER.md](PACKAGED_PROVIDER.md).
Media tools have a separate [source-build/synthetic-media gate](PACKAGED_MEDIA.md).
Full supported macOS-version
qualification, successful hosted launch evidence, controlled assets/checksums/release approval
and safe application replacement/recovery remain required. The existing plist's
minimum OS value is not evidence of compatibility on that OS. No release should
be offered solely because this narrow host job passes.
