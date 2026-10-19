# On-demand media inspection and per-item choices

Highlight a visible analysed row and click **Inspect Video…**. This explicitly
loads that video's metadata through the existing authenticated yt-dlp Python API,
with `noplaylist=True`, non-flat extraction, the same PO-token provider, player
JavaScript runtime and proxy. Applied account settings are used, not unsaved
Accounts edits. Only one inspection can run at a time. Extraction can make
multiple HTTP requests, and Auto keeps its established login-required fallback;
there is no eager extraction of the other playlist entries. Individual network
calls have a 20-second socket timeout and one extractor retry. These are not a
total wall-clock deadline or an instantaneous cancellation promise.

The resizable dialog reports actual media formats, container, codecs, height,
bitrate when reported, audio languages, manual subtitles and automatic captions.
Missing language data says **Not reported**. Original/default language labels
require the extractor's explicit `(original)` / `(default)` format labels; they
are not inferred from uploader, account identity or arbitrary language-preference
scores. A successful inspection does not prove a successful transfer or private
content permission.

## Choices and batch behavior

- Leave video/audio on automatic to retain batch quality and compatibility.
- Select a concrete video format or an audio-only track/language for this item.
  A concrete video choice takes precedence over the batch height cap. A video
  containing its own audio disables the separate audio override rather than
  pretending that an extra track will replace its embedded audio.
- Audio-only conversion disables video-stream selection. Existing conversion and
  compatibility processing remain in the downloader/FFmpeg path.
- Choose manual, automatic, or combined subtitles, check reported languages,
  then choose external files and/or embedding. No output is enabled against a
  language invented by the UI. Manual/automatic precedence follows existing
  yt-dlp subtitle handling when both report the same language.
- **Apply to this item** stores only that row's stream/subtitle overrides for
  future enqueueing. Other rows retain batch defaults; duplicate source URLs in
  different playlist rows do not share overrides. **Cancel** changes nothing.
- **Use batch defaults** explicitly clears the row override. The footer reports
  the count of overridden items. New analysis clears old row bindings. Once
  queued, options are copied to that job and survive queue serialization.

This provides per-item audio-track/language choice alongside existing batch
quality, codec and subtitle defaults. A global cross-video preferred audio-language
selector is not part of this checkpoint; audio IDs are deliberately item-specific.

## Revalidation and privacy

Metadata summaries retain no CDN/signed-stream URLs, subtitle URLs, cookies,
authorization headers or raw extractor notes. Internal additions do not expand
the qualified Swift wire DTO/schema.

Fresh extraction revalidates every explicit ID before transfer. yt-dlp selectors
use exact `format_id` predicates, so reported IDs such as `best`, `all`, `b` or
`mp4` cannot accidentally invoke selector grammar. The downloader updates both
yt-dlp's parameters and its compiled selector: mutating parameters alone leaves
`process_ie_result` using its constructor-time selector.

The one allowed HTTP 403 refresh first restores the captured batch selector to
obtain fresh metadata, then resolves automatic choices or revalidates explicit
ones. Automatic IDs may change; a vanished explicit choice fails clearly instead
of transferring another track. Authentication is never discarded to achieve a
format fallback. An open inspection cannot apply after input, applied account /
connection settings or runtime identity changes.

Selection support accepts plain alphanumeric / dot / underscore / colon / hyphen
format IDs, up to 128 characters. Other IDs are not offered as explicit choices;
this avoids injecting unsupported selector syntax. Summaries show at most 2,000
formats and explicitly disclose truncation. Refresh by inspecting again; cached
signed URLs are not reused.

## Validation limits

Deterministic tests use synthetic metadata and offline real yt-dlp selector /
`process_ie_result` behavior, including metadata refresh. They do not download
private media, inspect browser cookies, or certify live alternate-audio/subtitle
availability. The exact-ID and refresh tests also run against the isolated,
checksum-verified `2026.10.10.233141` nightly without activating it for the user.
Live user-authorized playback/stream/subtitle validation remains manual.
