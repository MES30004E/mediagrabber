# Native CI design and validation limits

The candidate workflow is `.github/workflows/migration-validation.yml`.
It continues deterministic Python tests and provides an independent hosted
macOS Swift job. It does not build a nonexistent Swift app or require the
owner's machine. Design approval and a future push are separate from executing
this workflow. No hosted Actions run has been requested or observed here.

## Jobs

1. Python: ubuntu-24.04, recursive submodule checkout, Python 3.12, distro-signed
   ffmpeg/ffprobe, wheels-only requirements, pip check and the full offscreen suite.
   Tests need binaries at resources/bin; symlinks use resolved installed Linux
   tools, never Mach-O assets. State is isolated under RUNNER_TEMP.
2. Swift: macos-15 hosted runner, recursive checkout, records Swift version.
   If no tracked Swift source/manifest exists, records an explicit not-run notice.
   Once native source exists, requires swift/Package.swift, builds and runs tests.
   This prevents a misplaced Swift file or missing manifest from silently skipping.
   Phase 2 must introduce an executable package plus at least one meaningful test;
   a zero-test run is not a readiness gate.

The expected future layout is a Swift package at swift/ for domain/client tests
and a minimal app executable. A later approved app-project workflow can add
xcodebuild on the hosted runner for UI tests and bundle packaging; SwiftPM alone
does not verify an installed .app, Info.plist, entitlements or Finder behavior.
The macOS job is currently only CI structure, not a native validation result.

Runner-provided toolchains are initially recorded, not claimed pinned. Before
native work, qualify a specific supported Xcode/Swift toolchain and macOS 12
deployment target on that runner, then pin its selection. macos-15 does not
establish Intel/arm64 release coverage: later separate architecture jobs must
prove bundled Python/Qt/native-tool compatibility. Add a macOS Python job when
qualifying actual platform integrations/packaging; Linux tests alone do not prove
Keychain/Finder/browser-cookie access.

## Trust and cache policy

Use checkout/setup-python actions pinned to full upstream commit SHAs. Only pip
download cache is reused, keyed by requirements/Python/OS through setup-python;
do not cache venvs, state, credentials, media, compiled Swift outputs or engine
binaries. No private cookies, signing secrets or notarisation are present.
Use pull_request rather than pull_request_target so untrusted code runs without
privileged repository context; token permissions are contents:read and checkout
credentials are not persisted. Private submodules would require a scoped binding,
but this provider submodule is public. No new PAT is assumed.

Requirements are ranges, not a reproducible lock. Baseline outputs remain a
dated result, and dependencies may vary in a future runner. Creating a lock and
trusted engine artifact manifest is separately planned release work; this design
does not invent hashes or disable package/TLS verification. Hosted Ubuntu apt
uses its configured signed repositories. Media tests prove required encoders
and local conversions; missing codecs must fail, not skip.

Workflow fails on pip check/build/tests and preserves exit codes. Swift source
absence is explicitly unrun, never reported as passing native tests. No automatic
artifact upload can accidentally export histories/cookies. Add curated artifacts
only after privacy review of exact paths. Local Cloud checks validate YAML and
embedded shell/guard logic; they cannot prove hosted macOS builds, Actions token
permissions, runner availability or native behavior.

## Later packaging lane

Add packaging only after a native app exists and its architecture is qualified.
Run unsigned/ad-hoc internal smoke without certificate secrets first. Authorized
release jobs may later sign/notarize with separately configured secure bindings.
Do not invoke the baseline build_macos.sh during deterministic CI: it bundles,
downloads architecture-specific tools and signs, beyond early source-test scope.
