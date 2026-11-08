# Install the operator panel on Android

Open the workstation's private HTTPS address in Android Chrome with Tailscale
connected. Choose **Install app** from Chrome's menu, or open station details
and use **Zainstaluj aplikację** when Chrome offers its install event. The OS
installation confirmation belongs to the operator. Browser engagement/platform
rules may delay the event; the menu remains the fallback. The existing HTTP
address remains available but cannot register this secure web application.
Keep hostnames and allocated ports in ignored workstation deployment records.

## Runtime boundary

The manifest has a stable root identity, start URL and scope, standalone display,
192/512 PNG icons and a separate padded maskable icon. Icons are rendered from
the existing favicon with `scripts/generate-app-icons.cjs`; provide Playwright in
the development runtime or through NODE_PATH. `ui/index.html` links the manifest;
`npm run build` under `ui/` regenerates the live HTML/JS/CSS.

The service worker caches only the noninteractive offline HTML/CSS. API status,
control tokens, jobs, files, camera, application JS and commands stay network-only.
There is no command queue, background sync, reconnect to USB, forced page reload
or automatic machine execution. Returning to the app requires fresh status before
manual controls become available. Offline navigation shows no controls/readings.

Serve only the explicit manifest, service-worker, offline and icon routes through
the normal handler. Existing no-store response headers also cover the manifest,
worker and API. HTTPS must proxy the same existing loopback server; preserve all
other private routes and do not enable Funnel. The live service and collection
remain the same across HTTP/HTTPS; origin-local installation is separate.

## Evidence, 2026-11-08

All 120 hardware-free Python checks passed in an isolated tree on the RPi target;
PWA lifecycle/install-event/network-boundary checks passed in Node. Desktop
Windows loopback HTTP tests intermittently aborted unauthenticated requests with
WinError 10053; the same complete suite passed on the Linux deployment target.
Normal-profile Chrome reported zero manifest/installability errors. Ephemeral
incognito contexts correctly reported in-incognito and were not treated as
installable. Desktop/mobile captures, offline navigation/recovery and cache
inventory checks passed. No actual Android launcher installation or physical
machine operation was performed. The CNC stayed disconnected with an empty job.

The scoped deployment preserves pre-existing calibration/UI work, with exact
source/asset checks and a rollback backup. Allocation and backup paths are in
ignored `.local/pwa-deployment.json`; user readiness was confirmed before restart.
