# Instagram Private Media Resolver (static)

This directory contains a privacy-first static helper for media that the user is already authorized to view on Instagram.

## What it does

1. The static page accepts an Instagram URL and opens it in the user's own logged-in Instagram tab.
2. A bookmarklet named **MG Capture** runs on `instagram.com`.
3. The bookmarklet inspects media that is already loaded in that page (`video`, `img`, Open Graph media, and loaded Instagram CDN video resources).
4. It opens the static resolver page with a short-lived payload in the URL fragment.
5. The resolver immediately removes the fragment from the visible URL and presents the discovered media as a local result library.

The app also includes an advanced local-only parser for an Instagram GraphQL JSON response.

## Privacy properties

- No backend service.
- No analytics.
- No third-party JavaScript.
- The page never asks for Instagram cookies, passwords, CSRF tokens, Authorization headers, or request headers.
- CSP sets `connect-src 'none'`, so page JavaScript cannot make Fetch/XHR/WebSocket connections.
- Media previews are allowed only from Instagram / Meta CDN hosts.
- Results are not written to localStorage or IndexedDB.
- The bookmarklet only accepts media URLs hosted on Instagram/Meta CDN domains.

## Important GitHub Pages note

A **private repository does not automatically mean a private GitHub Pages site**. GitHub's current access-control documentation says privately published Pages sites require an organization using GitHub Enterprise Cloud. Personal-account Pages sites should be treated as public.

This tool is therefore designed so that publishing the static UI publicly does not expose credentials or create a credential-handling backend.

## Deployment

The repository includes a manual GitHub Pages workflow at:

`.github/workflows/deploy-private-instagram-tool.yml`

The workflow is intentionally `workflow_dispatch` only, so merging the code does not publish anything by itself.

To deploy:

1. In repository **Settings → Pages**, set **Source** to **GitHub Actions**.
2. Open **Actions → Deploy private Instagram resolver**.
3. Run the workflow manually.
4. Open the published Pages URL.
5. Drag **MG Capture** to the browser bookmarks bar.

## Limitations

- A pure GitHub Pages app cannot read Instagram authentication cookies because it is a different origin. This is a browser security feature, not a bug.
- The bookmarklet can only capture media that Instagram has already loaded into the current page/browser context.
- For carousels, move to the desired slide and run the bookmarklet again if that slide was not yet loaded.
- Instagram CDN URLs are signed and expire.
- Cross-origin `download` behavior is browser-dependent; **Open / Save** always exposes the direct signed media URL so the user can save it from the browser.

Use this only for media you are authorized to access.
