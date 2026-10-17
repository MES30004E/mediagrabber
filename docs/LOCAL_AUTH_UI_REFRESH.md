# Local authentication and UI refresh

Local branch: `improvement/auth-ui-refresh`, based on qualified Phase 2 commit
`b603921f92dcf5238e6451ba46346ebe450bedfb`. Swift source/CI and published branches
are not modified. This task does not implement Phase 3. Work remains local.

## Checkpoint A — account connection

Settings → Accounts → YouTube offers Connect, browser/profile detection,
Sign in using browser, Verify Connection and Disconnect. Connect selects the
existing Browser Cookies mode; Apply/OK saves the choice for existing analysis,
queue and download paths. Cancel leaves saved settings untouched. Disconnect
disables future cookie use after Apply; it does not log out the browser, revoke
Google sessions or alter running tasks. Reset restores existing Auto defaults.

Detection reads app locations and profile metadata only, including Firefox
profiles.ini. Cookie extraction/decryption remains yt-dlp's responsibility.
Safari/Firefox/macOS access can require user permissions; discovery is not proof
that a database is readable. Browser sign-in opens the selected installed browser;
the user must select the same profile there. No incognito export, app-owned
browser profile, Qt WebEngine or Google password form is added.

Verification is intentionally different from Auto extraction: it explicitly tests
the configured fallback cookie source while Auto download behaviour stays
public-first. It reads the in-memory yt-dlp cookiejar, then a bounded YouTube
account page and a strictly boolean LOGGED_IN server configuration. Missing page
configuration is unconfirmed, never authenticated. No playlist/history entries
are enumerated or displayed. A server-confirmed session is **not proof of private
playlist ownership, entitlement, working formats or PO-token readiness**. Those
are checked by the existing extraction/download paths. None mode tests public
connectivity only. Verification does not rewrite imported cookie files.

Results distinguish readable/missing cookies, signed-out/rejected sessions,
rate limiting, additional verification, provider requirements and unavailable
connections with fixed safe text. Browser/profile/file/network edits invalidate
verification; stale task results cannot overwrite the new state. Network tests
now use the selected Direct/System, custom HTTP/SOCKS5h or available Tor route,
including configured proxy credentials without displaying them. Verification
does not start Tor, rotate circuits or fall back to Direct on routing failure.

### Embedded browser feasibility and references

Google restricts embedded user agents at its authentication endpoint. Qt
WebEngine cookies are not a supported yt-dlp cookiesfrombrowser source; exporting
an embedded/guest jar would introduce session handling and still not prove Google
sign-in works. A dedicated external profile is technically a separate option,
but would introduce profile lifecycle/locking/cleanup without removing the need
for browser permissions. This implementation uses existing supported browser
profiles, with explicit user-controlled Netscape cookies.txt import as fallback.
It never exports all browser cookies or uses an OAuth-to-yt-dlp conversion.

- [Google embedded-agent restrictions](https://developers.google.com/youtube/reporting/guides/authorization/server-side-web-apps)
- [Upstream YouTube cookie and OAuth guidance](https://github.com/yt-dlp/yt-dlp/wiki/Extractors)
- [Apple sidebar guidance](https://developer.apple.com/design/human-interface-guidelines/sidebars)
- [Downie workflow/interface reference](https://software.charliemonroe.net/downie/)
- [Transmission utility reference](https://transmissionbt.com/)

## Verification boundaries

Automated checks use synthetic cookies, profile metadata and mocked network
responses only. No personal browser cookie database or Google account is read
by tests. A live authorised Mac check is still needed for browser permissions,
site-response changes, private-resource access and downloaded output. Do not
describe offscreen screenshots as Finder/Accessibility or live-account QA.

No new runtime dependency is required. Existing PyInstaller source discovery
includes the new Python modules; there is no WebEngine dependency.
