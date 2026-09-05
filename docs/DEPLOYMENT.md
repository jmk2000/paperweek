# Deployment routes

**v0.4 unattended server:** use [BACKEND.md](BACKEND.md) and Docker/NPM. Static GitHub Pages cannot run its Python backend, store server credentials or perform scheduled synchronisation. The original Pages workflow below is only a legacy browser demonstration.

---

# Deployment and Android

Paperweek is a static browser app. Deploy code/assets, not household settings or calendar
exports. No backend or always-on Mac is needed once the static build is hosted over HTTPS.
A browser connection to Google still expires; static hosting does not solve unattended OAuth.

## Public GitHub repository

Start from the clean source archive rather than committing an old prototype's review files.
Run the privacy check and inspect what Git will publish. The source uses only generic demo
labels. The GitHub repository owner/name is your choice; nothing in the application assumes it.

```sh
python3 tools/privacy_check.py
git init
git add .
git diff --cached --stat
python3 tools/privacy_check.py --tracked
```

Review the staged content before committing. `.gitignore` prevents typical accidental file
additions, not past commits or a manual drag-and-drop upload to GitHub. Check screenshots and
history yourself. Enable repository secret scanning where available. Add your actual remote
only after the review. This distribution does not create or publish a repository for you.

## GitHub Pages workflow

1. Push the source, including `.github/workflows`, to the repository you control.
2. In repository Settings → Pages, choose **GitHub Actions** as the build/deployment source.
3. Let **Build and test** finish. It tests the C core, JavaScript and actual LVGL browser build.
   The workflow has not been run for this distribution; inspect any build failure instead of
   assuming the source has already passed it.
4. Under Actions, run **Publish web app** manually. Choose `lvgl` for the actual LVGL frontend
   or `preview` for the lighter browser-font version. Only that built static directory is uploaded.
5. Open the Pages URL in Chrome on the tablet. Configure names and Google settings **there**.

Public source/site files do not contain your browser settings or fetch private events on behalf
of anonymous visitors. Every browser needs its own settings and Google authorisation. Nevertheless,
anyone who can alter the scripts hosted at that origin could compromise data shown by those scripts.
Protect the repository and hosting account, and avoid running unrelated untrusted apps on the same
origin. A dedicated HTTPS origin offers clearer isolation than many apps sharing one origin.

GitHub Pages project paths are supported: module imports, WASM files, manifest and service-worker
scope are relative, not hard-coded to `/`. The OAuth origin omits the project path. The workflow
requests deployment permission only in its deploy job and is not triggered by pull requests.

## Another static HTTPS host

Upload only `dist-lvgl/`, `dist-preview/`, or the supplied `site/` contents. Serve `.wasm` as
`application/wasm` and `.mjs` as JavaScript. Preserve relative filenames. Do not serve the source
folder, OAuth credentials or private exports as the website root. The app fetches no runtime
configuration file: household settings are entered locally in the browser.

A host can set these response headers in addition to the supplied page CSP:

```text
Referrer-Policy: no-referrer
X-Content-Type-Options: nosniff
Cross-Origin-Opener-Policy: same-origin-allow-popups
```

Avoid a restrictive `Cross-Origin-Opener-Policy: same-origin` setup that breaks popup communication.
The app uses single-threaded WebAssembly and does not require cross-origin isolation/SharedArrayBuffer.
The supplied CSP allows its own scripts, WASM compilation and the Google Identity Services endpoints;
live OAuth under that policy still needs an on-device acceptance test.

## Tablet installation

In Chrome, open the HTTPS app and use Install / Add to home screen when available. Browser menus
vary. A full-screen request is also provided. “Keep awake” requests a screen wake lock after a user
press and reacquires it when returning to the foreground where permitted. The OS/browser may still
release it. Use the tablet's screen/power settings for a reliable demonstration and keep it powered.

The layout keeps a 4:3 canvas without stretching. A widescreen tablet will have unused space; it is
not a millimetre-accurate panel simulation. The page does not claim to calibrate physical pixel size.
No APK, Android background service or device-owner/kiosk policy is installed.

## Offline and updates

The service worker caches an **explicit allowlist of public app files only**. It never caches
Google API responses. A changed build gets a content-derived cache version and waits for the old
app's tabs/windows to close before activation. Close all Paperweek windows and reopen after updating.
During a session, already-loaded private events remain only in RAM; after reload while offline,
only the demo can be regenerated. Do not describe this as an offline private-calendar cache.

## References

[GitHub Pages custom workflows](https://docs.github.com/en/pages/getting-started-with-github-pages/using-custom-workflows-with-github-pages),
[MDN: installable PWAs](https://developer.mozilla.org/en-US/docs/Web/Progressive_web_apps/Guides/Making_PWAs_installable),
[MDN: Screen Wake Lock API](https://developer.mozilla.org/en-US/docs/Web/API/Screen_Wake_Lock_API).
