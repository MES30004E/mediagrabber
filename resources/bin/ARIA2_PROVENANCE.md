# Bundled aria2c provenance

- Version: aria2 1.37.0
- Architecture: native macOS arm64, deployment target macOS 12.0
- Upstream release: https://github.com/aria2/aria2/releases/tag/release-1.37.0
- Official source archive: https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0.tar.xz
- Source SHA256: `60a420ad7085eb616cb6e2bdf0a7206d68ff3d37fb5a956dc44242eb2f79b66b`
- Bundled binary SHA256: `d14ac3571aaf35d8a0a68436b4c3b537c17abca1bcbaed17215f3c4f18d3b5bb`
- License: GPL-2.0-or-later with the upstream OpenSSL linking exception

The official release does not contain a macOS executable. This binary was built locally on Apple Silicon from that official release archive by `scripts/build_aria2c_macos.sh`; it was not taken from a third-party binary host. The build enables BitTorrent, HTTPS through AppleTLS, gzip, and Apple system message-digest support. It links only Apple system frameworks/libraries and does not require Homebrew or a global installation.
