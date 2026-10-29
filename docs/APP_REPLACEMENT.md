# Verified-copy replacement primitive

`morgan_media_downloader.app_installation` is a replacement primitive, not a
complete application updater. It is wired into the existing `build_macos.sh`
instead of deleting the destination before copying. The legacy builder remains
unqualified for releases; do not execute it on the licence-constrained local Mac.

The primitive copies a candidate into a private directory on the destination
volume, verifies its expected bundle identity and strict deep code signature,
and only then moves the old app into a retained sibling backup. It validates the
activated copy again. Activation failures attempt restoration; restoration
failures preserve the backup and report its path. No previous backup is claimed
for a first installation. The candidate source is never deleted.

The caller must close the app first. A conservative macOS process check refuses
replacement while a matching app or bundle process is present; it does not kill
processes. A private nonblocking lock serializes cooperating installers,
including parent-directory aliases. Destination identity changes during candidate
validation are rejected. If another actor recreates the destination during failed
activation, that app is not moved or deleted to make room for rollback.
Rollback also checks the activated candidate's directory identity before moving
the destination; a foreign replacement during post-activation validation is
preserved with the previous backup for manual recovery.

## Destination remains unresolved

The preferred path is still the external project's
`dist/Morgan Media Downloader.app`. The user explicitly chose to **decide later**
about any alternative destination. My Passport was observed as exFAT, while the
bundle uses symlinks. Preflight tests symlink preservation and rename behavior in
an owned temporary directory on the selected volume and refuses installation if
unsupported. It does not choose a fallback, convert the filesystem, install a
launcher or delete the existing app. No real local installation has been run.

## Qualification and remaining work

`tests/test_app_installation.py` uses synthetic app directories, injected copy and
validation functions, simulated process output and fault injection. These cover
retained backups, pre/post-activation failures, failed restoration, first install,
unsupported volumes, running apps, symlinks, competing installers and destination
races. They do not qualify real `ditto`, macOS process discovery or signature
validation on a packaged app; those require hosted macOS integration evidence.

`scripts/check_packaged_replacement.py` adds that hosted-only integration gate.
It uses the real signature/copy/process checks to install into a new runner-owned
temporary directory, replaces that synthetic installation, verifies that the
previous directory is retained by identity, compares file contents and symlink
targets against the untouched source, and launches the replacement through the
isolated frozen Cocoa diagnostic. Its temporary copies are disposable CI fixtures,
not user installations. Inspect the exact run/commit before claiming it passed.

A strict code-signature check alone does not establish publisher trust or release
approval. The existing packaging signature is ad-hoc, not Developer ID signing or
notarisation. This primitive does not download releases, verify asset checksums,
select versions/channels, coordinate a post-exit helper, persist a crash-recovery
journal, expose rollback UI or automatically recover after power loss between
renames. Those remain required before describing the application updater as
complete. Retained backups must not be automatically deleted until a separately
validated retention/rollback policy exists.
