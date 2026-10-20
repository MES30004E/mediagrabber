# Hosted media-tool integration

`scripts/prepare_media_bundle.py` builds fresh sources on hosted arm64 macOS only.
It never consumes or overwrites the developer's existing `resources/bin` files,
venv or installed app. This is an integration build, not a release installer.

## Sources and configuration

| Tool | Official source | SHA-256 |
| --- | --- | --- |
| FFmpeg / FFprobe 9.0.2 | `https://ffmpeg.org/releases/ffmpeg-9.0.2.tar.xz` | `8c3850283eb25fa026482078a04051e0be17347b09ef81a0849bec15a96e002e` |
| aria2 1.37.0 | `https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0.tar.xz` | `60a420ad7085eb616cb6e2bdf0a7206d68ff3d37fb5a956dc44242eb2f79b66b` |

Checksums precede extraction/execution. Bounded archive extraction rejects path
traversal; all compilation occurs in newly owned temporary directories. A complete
stage is activated by rename only after binary version/configuration and encoder
checks. Existing destinations, including symlinks, are refused.

FFmpeg uses explicit external libraries with automatic detection disabled. Hosted
Homebrew supplies the source build's codec dependencies (`aom`, `lame`, `opus`,
`libvpx`, `x264`, `x265`) and build tools. Both pkg-config and explicit compiler/
linker paths are supplied: FFmpeg's LAME check does not use pkg-config.
Homebrew verifies its downloads;
`codec-build-formulae.json` records current formula metadata rather than claiming
those packages are independently pinned by this repository. The official standard
[FFmpeg formula](https://formulae.brew.sh/formula/ffmpeg) does not include all the
encoders this app exposes, so its binary is not silently substituted.

Required encoders are libx264, libx265, libvpx-vp9, libaom-av1, aac, libmp3lame,
libopus and flac. Missing encoders or `--enable-nonfree` reject the build.
FFmpeg enables GPL/version3, Apple audio/video frameworks and SecureTransport.
aria2 retains the existing source build's AppleTLS/static configuration. The
hosted deployment target is macOS 15.0; this is not evidence of macOS 12 support.

`media-build.json` records source URLs/checksums, configure options, version
responses and pre-relocation binary hashes. PyInstaller changes load paths and
signatures, so those hashes identify build inputs, not final release assets.
Upstream COPYING files accompany the stage. Complete corresponding source,
third-party dependency licences/notices, application licensing and distribution
obligations still need review before publishing any asset. This document is not
licensing clearance. The developer's old nonfree FFmpeg binary is not reused.

## Actual-bundle tests

The spec accepts `MORGAN_MEDIA_STAGE` and collects all three executables as BINARY
inputs, allowing PyInstaller to discover/relocate dependent libraries. The shared
Mach-O gate rejects external runpaths and unresolved/non-contained dependencies.

`scripts/check_packaged_media.py` runs only the actual bundle paths with a
restricted PATH, temporary HOME/cache/cwd and no dyld overrides. A generated
32×32 video and synthetic sine wave exercise H.264/AAC, HEVC, VP9, AV1, AAC,
MP3, Opus and FLAC encoding plus stream-copy remux. FFprobe must confirm exact
codec streams, nonempty output and bounded positive duration for all nine cases.
aria2 must return the pinned version; no torrent/network transfer is performed.
No personal media, cookies or Keychain items are used. Strict ad-hoc signature
verification, real native-host checks and offline Node/provider checks remain
required in the same hosted job.

## Remaining release gates

No uploads, tags, releases or local installations occur. GUI launch, deployment
version compatibility, live authenticated downloads, full corresponding-source/
licence review, approved versioned assets/checksums/notes, signing/notarisation
requirements and safe application replacement/recovery remain separate work.
This gate does not claim the Python conversion UI's complete interaction flow or
actual torrent transfers have been exercised.
