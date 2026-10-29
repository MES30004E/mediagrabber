# Development app archives

This is a development-candidate format and hosted round-trip check, not a public
release, application updater or permission to publish. No assets are uploaded.

`app_archives.build_development_archive` creates a new output directory containing:

- `Morgan-Media-Downloader-VERSION-macos-arm64.tar.gz`, preserving bundle symlinks;
- `release.json`, recording version, source commit, platform/architecture, minimum
  macOS and the archive's SHA-256/byte size;
- `SHA256SUMS`, covering the archive and `release.json`;
- `RELEASE_NOTES.md`, explicitly describing an unapproved development candidate.

The metadata always says `channel: development` and `publication_approved: false`.
The bundle's identity/version, thin arm64 Mach-O executable header and deployment
target must agree with the candidate. Native signature validation reuses the
existing strict deep verification. This does not establish Developer ID publisher
trust, notarisation, source/licence compliance or live download success.

`extract_development_archive` checks development metadata, archive name, size and
SHA-256 before extraction. It rejects absolute/traversing paths, duplicate and
case/Unicode-normalized colliding entries, escaping symlinks, devices and hard
links. Hard-linked source files are materialized as ordinary files when building.
Limits are 2 GiB compressed, 6 GiB expanded and 100,000 members. Python's data
extraction filter additionally checks resolved paths while processing links.
The caller's archive is copied into a bounded unlinked private snapshot; that
same owned snapshot is hashed and parsed, so later pathname or in-place source
changes cannot substitute different bytes. After extraction, the complete
resolved symlink graph must remain inside the actual app root, not merely inside
the enclosing temporary stage. This also rejects chained aliases out of the app.

Extraction occurs in a fresh private stage, verifies the reconstructed bundle and
only then exposes a new destination. Existing destinations are refused. Building
inside the source bundle is refused without creating directories inside it. This
format is not a general-purpose untrusted-file unpacker or a stable update feed.

Hosted integration must launch the actual extracted app using the isolated Cocoa
startup diagnostic and compare its source fingerprint. Source fixture tests inject
validation and never execute Apple tools. Inspect exact hosted logs before
claiming native archive compatibility. The user's preferred exFAT destination is
still unresolved; these archives do not choose a replacement destination.

The workflow invokes `scripts/check_packaged_archive.py APP GITHUB_SHA` after the
existing actual-bundle checks. Its default native verification is refused outside
hosted arm64 macOS. It builds/extracts into an owned temporary directory and emits
only a bounded candidate summary, then removes those disposable CI copies. No
upload action or release API is involved. Passing this probe is evidence for that
exact built archive round-trip, not approval to distribute it.

Remaining work includes approved version/channel promotion, protected publication
workflow, corresponding source/third-party notices and the application's licence,
tokenless release download and compatibility selection, post-exit installation,
durable crash recovery and rollback UI. Checksums delivered with an archive prove
consistency, not independent publisher authentication. No stable release is created
by a development commit or this check.
