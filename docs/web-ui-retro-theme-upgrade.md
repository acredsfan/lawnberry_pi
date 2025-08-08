## Web UI Retro Theme & Build Integration Upgrade

Date: 2025-08-07

### Summary
Implemented a first-class 80's sci‑fi / neon theme aligned with the LawnBerryPi logo and improved production alignment between the Vite build output and FastAPI static mounting. This removes fragile workarounds and ensures a reliable, high-performance path for both development and production on Raspberry Pi OS (aarch64) Bookworm.

### Key Changes
1. Added `base: '/ui/'` to `vite.config.ts` so all emitted asset URLs resolve correctly when FastAPI mounts `web-ui/dist` at `/ui`.
2. Corrected WebSocket dev proxy target from port 9002 to the FastAPI backend (8000) to match the actual runtime topology.
3. Tightened build configuration for ARM64 (no large sourcemaps, explicit chunk size boundary, ES2018 target) for faster builds on Raspberry Pi.
4. Upgraded `index.html` to dark neon loading screen with animated scan bar + logo, removing conflicting light mode inline styles.
5. Refactored App initialization loader to use non-blocking neon progress styling with graceful degraded mode messaging and a manual continue action.
6. Ensured theme fonts (Orbitron, Share Tech Mono) are preconnected / performant.
7. Added deterministic hydration marker removal + watchdog fallback (prevents infinite loading screen in failure modes).
8. Implemented global window error & unhandledrejection overlay in `index.html` to surface fatal pre-React errors (avoids silent blank screen).
9. Added `<ErrorBoundary>` wrapper plus persistent localStorage error log (`lbp_errors`).
10. Hardened runtime access patterns (replaced unsafe chains like `status?.state.toUpperCase()` with `status?.state?.toUpperCase()`; guarded battery & coverage numeric formatting to prevent `undefined.toFixed()` and similar TypeErrors during early load / mock data states).
11. Added route-level React.lazy + Suspense for major pages (Dashboard, Navigation, Maps, Documentation, etc.) to reduce initial bundle parse cost on Raspberry Pi.
12. Refined Rollup manualChunks: separated router, maps (leaflet & google loader), charts, and UI libraries for improved browser caching and incremental hydration performance.

### Rationale (No Workarounds Policy)
Previously the UI depended on default root-relative asset paths (`/assets/*`) which break when the static bundle is **namespaced at `/ui`** by FastAPI. Setting `base: '/ui/'` eliminates the need for server-side path rewrites or additional reverse-proxy rules.

### Performance Considerations (Bookworm / ARM64)
- Disabled heavy sourcemaps for normal builds.
- Explicit manualChunks retains predictable caching for vendor, UI core, and map libs.
- ES2018 target keeps transpilation minimal while compatible with Chromium-based kiosk builds.

### Theming Principles Applied
- Palette cyan / magenta / yellow triad with accent purple & orange mirrors logo vibrancy.
- High-contrast dark surfaces (`#0a0a0a`, `#1a1a2e`, `#16213e`).
- Neon border & glow animation tokens consolidated (reused `neon-border`).
- Typography uses Orbitron + Share Tech Mono for retro-futuristic instrumentation feel.

### Follow-Up Opportunities
- Introduce theme density toggle for low-power mode (reduce animations for battery).
- Add prefers-reduced-motion media query fallbacks.
- Implement progressive hydration metrics logging (first paint vs WebSocket ready time).
- Consider pre-splitting Leaflet & Google Maps into an async route-level dynamic import.

### Validation Steps
1. Build: `npm run build` (should emit assets under `dist/` referencing `/ui/` paths).
2. Backend auto-mount logs: look for `Mounted web UI static assets at /ui`.
3. Access: `http://<pi-host>:8000/ui/` should load neon theme without 404s.
4. Dev mode: `npm run dev` then browse `http://<pi-host>:3000` (WebSocket proxies to backend 8000).
5. Runtime Hardening: Temporarily force no status payload (simulate) — UI should still render with fallback labels (UNKNOWN / 0%) and no crash overlay.
6. Error Capture: Intentionally throw inside a component (e.g. add `throw new Error('TEST')` in a child) → ErrorBoundary overlay appears; remove throw → normal UI resumes after rebuild.

### Rollback
Revert `vite.config.ts`, `index.html`, `App.tsx` and delete this doc if necessary. No schema or API coupling changes were introduced.

---
Maintainer: Web UI / Frontend Subsystem
