# Playlist workspace

The existing Python application now keeps the checked download set separate from
the visible filter and highlighted preview row. No Swift migration changes are
part of this checkpoint.

## Selection

- Filter already-analysed titles, uploaders/artists, sources or playlist indices.
  Filtering is local; it does not reanalyse videos or fetch private libraries.
- **Select All Visible** checks matching rows without changing hidden choices.
- **Select None** clears every check, including hidden choices.
- **Invert Visible** changes only matching rows.
- The footer reports selected, visible and total counts. Hidden checked items
  remain in **Download Selected**, preserving the queue's original ordering and
  torrent file indices. Clear the filter to inspect the full set.
- Highlight multiple rows with Shift or Command/Control. **Space** toggles the
  highlighted visible rows together. Highlighting alone does not change checks.
- Editing the analysed input disables enqueueing until analysis is refreshed;
  changing checkboxes or filters cannot bypass that safeguard.

## Space and preview

Download Options (batch defaults) and Media Preview start collapsed on a fresh
installation. Their disclosure states and the table/preview splitter sizes are
saved with local preferences. Expanded options scroll independently; the queue
action footer remains outside the scrolling content. More Options uses a narrow
two-column layout rather than stretching the entire page horizontally.

**View → Full Screen** uses the native Qt/macOS fullscreen window behavior
(Control-Command-F on macOS, F11 elsewhere). Native window-state changes update
the menu. Closing or saving in fullscreen retains the normal window geometry,
not the screen-sized fullscreen geometry. Actual macOS green-button interaction
still needs manual validation; deterministic tests use Qt offscreen windows.

Preview follows the current row and shows reported duration/subtitle metadata.
Thumbnails load only for the current row while preview is expanded, not for all
828 entries. Changing rows cancels the old task; only one thumbnail worker is
allowed, with one pending latest-row request rather than an accumulating queue.
Cancellation is checked before network work, between chunks and before cache
activation. An already-blocked socket call can still wait up to its 20-second
timeout; the UI remains responsive and does not start overlapping fetches.
Unique atomic partial files also protect same-URL cache writes. Late progress/results cannot
replace the current image. A selected proxy/Tor route that is unavailable blocks
the thumbnail request instead of silently using Direct. No personal cookies or
private media are used in the automated preview tests.

## Remaining media-detail work

This checkpoint does not yet implement per-video format/audio-track inspection,
original/default or alternative audio-language controls, or per-item format and
subtitle overrides. Existing batch subtitle-source/language/external/embed
options remain available. Empty metadata is labelled **Not reported**, not
invented as a language or a claim that a stream is absent. Expensive individual
metadata inspection will be an explicit on-demand operation in the next
checkpoint; there is no eager 828-video extraction here.
