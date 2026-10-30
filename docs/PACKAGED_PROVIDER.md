# Bundled Node and pinned provider integration

This is a hosted packaging integration gate, not a distributable release.
No local Apple build tools, Homebrew, administrator access or installation are
required. The upstream provider remains a pinned submodule at
`7608dd51ee813b48cf9a6d68c6e42cb197ce10e0` (1.3.1); its HTTP/script implementation,
proxy handling and token generation have not been rewritten.

## Inputs and isolation

`scripts/prepare_provider_bundle.py` accepts only hosted arm64 macOS CLI execution.
It downloads Node v24.22.0 from the official fixed nodejs.org archive and checks
SHA-256 `75ddfb875bbd868ebe57536f4442225f54dd10f6d2178dd439de869a5c648dc3`
before extraction/execution. It validates the provider pin and tracked changes,
copies only tracked source files into a fresh temporary stage, and never runs npm
in the user's submodule checkout. Existing destinations are not replaced.

The upstream package lock controls npm inputs. Lifecycle scripts are disabled
during `npm ci`/production pruning; only Canvas is explicitly rebuilt from source
using the verified Node headers, hosted Python and hosted Cairo/Pango libraries.
TypeScript compilation, native Canvas PNG generation and the provider's offline
`--version` must pass before atomically activating the stage. Node/upstream
licenses, lock digest, exact version/pin and hosted formula metadata accompany it.
This records inputs; it is not complete third-party release-license clearance.

### Canvas runtime-only build payload

Hosted diagnostic run `40989481899` on `0242acb` identified the extracted archive's
strict-signature failure at
`canvas/build/Release/obj__dot__target/canvas/src/ImageData.o`: "code object is not
signed at all". File contents/symlinks and modes matched the signed source.
Canvas's actual `lib/bindings.js` requires only `build/Release/canvas.node` from
that build tree. Compiler objects and Makefiles are not runtime requirements.

The owned temporary provider stage now retains only that required add-on in the
Canvas build tree, before normal PyInstaller signing. Source/runtime JS, package
licences, compiled provider JS and the upstream checkout are preserved. The
existing PNG/version checks still run **after** pruning. No extracted app is
modified or re-signed and strict archive signature validation is unchanged.

PyInstaller's installed `building/osx.py` documents why signatures of non-runtime
objects under Frameworks can be stored in extended attributes and lost by
transports that do not preserve them. The hosted failure and byte/mode comparison
fit that mechanism; a new actual hosted round-trip must qualify this fix before
claiming the release blocker resolved. Portable staging tests reproduce retention
of the offending compiler object before the fix and verify its removal while
retaining the loadable add-on afterward.

## Bundle and checks

`MORGAN_PROVIDER_STAGE` opts the PyInstaller spec into staged Node/provider files.
Native Canvas add-ons are BINARY inputs so PyInstaller can collect and relocate
their dependent libraries. Frozen runtime discovery prefers the bundled Node and
provider server; an explicit provider-home setting still takes precedence. Source
development and existing proxy/authentication behavior remain unchanged.

`scripts/check_packaged_provider.py` runs the actual bundled Node/provider with a
restricted PATH, clean Node/Python/dyld environment and temporary working/cache
directories. It checks versions and a native Canvas PNG buffer without cookies,
Keychain, live media or generating a PO token. A Mach-O gate rejects external
non-system load paths/rpaths and requires relative dependencies to resolve to
existing files inside the bundle. Hosted strict ad-hoc signature verification
and the separate real Companion protocol probes remain mandatory.

## Explicit exclusions

The staged spec does not silently include the old ignored `resources/bin` media
binaries. Local inspection found FFmpeg 6.0 configured with `--enable-nonfree`,
despite the old download script naming a different release. Those existing files
are preserved locally but are not an approved public-release input. A maintained,
integrity-checked FFmpeg/FFprobe/aria2 payload now has a separate
[hosted source-build and synthetic-media gate](PACKAGED_MEDIA.md); matching source
and licensing review remain required before distribution. No full app launch,
authenticated download, minimum-macOS compatibility or release approval is
implied by these integration gates. No assets are uploaded and no tags/releases
are created. Signing/notarization and application replacement/rollback remain
separate work.
