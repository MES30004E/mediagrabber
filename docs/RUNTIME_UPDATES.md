# Runtime update history and cadence

The existing `YtDlpRuntimeManager` remains the only yt-dlp installer. Settings →
Updates shows active/bundled versions, latest known stable and nightly releases,
independent successful-check times and errors for each channel, successful-update
time, current operation status and rollback choices. These are separate facts:
a successful release check is not a successful installation or media download.

Automatic stable checks use a persisted daily interval. An enabled app checks at
startup and wakes hourly while open, but contacts GitHub only when due. Failed
release checks back off for one hour. Turning off the existing startup-check
preference also stops future background checks; changing that preference does
not cancel an operation already dispatched. Manual **Check Now** and **Update
Now** bypass the interval. No automatic nightly update is introduced.

The metadata ledger is private, user-local, atomically replaced and backward
compatible with older metadata. Last successful check/version survives a failed
check. Redacted release-check and installation errors survive restart. Successful
checks clear release-check errors; a successful installation clears the current
installation error. It is not a full audit trail of every historical failure.

Concurrent checks on the same manager serialize through activation. Existing
download attempts still retain the runtime snapshot captured at dispatch. SHA256,
archive/version and provider import checks precede activation; no new upstream
pull, unverified executable or alternate runtime directory is introduced.

Rollback lists the stored previous version and bundled fallback. The existing
rollback implementation revalidates stored artifacts when used and falls back
to bundled if a previous artifact is missing, corrupt or incompatible. A listed
previous version is not a promise that an externally modified file is usable.

## Scope still outstanding

The [Updates & Components screen](COMPONENT_UPDATES.md) now provides inventory,
release metadata and explicit compatibility/update-policy limits for the app,
provider, FFmpeg/FFprobe and Cookie Companion. It does **not** yet install or roll
back those non-yt-dlp components. Hosted packaging, app launch
qualification and staged application replacement/rollback also remain pending.
No application release is published by a runtime action or development commit.
