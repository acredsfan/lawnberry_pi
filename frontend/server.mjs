// Simple production server for LawnBerry frontend
// - Serves static files from dist/
// - Proxies /api -> backend /api/v2
// - Proxies /ws (WebSocket) -> backend /api/v2/ws/telemetry

import express from 'express'
import path from 'path'
import { fileURLToPath } from 'url'
import compression from 'compression'
import morgan from 'morgan'
import { createProxyMiddleware } from 'http-proxy-middleware'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const app = express()
const PORT = process.env.PORT || 3000
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8081'

// Logging & compression
app.use(morgan('combined'))
app.use(compression())

// Serve branding assets (e.g., LawnBerryPi_Pin.png) so they are available to the UI
const brandingDir = path.resolve(__dirname, '../branding')
app.use('/branding', express.static(brandingDir, { maxAge: '30d' }))
// Back-compat: expose the primary mower pin at the root path expected by the editor
app.get('/LawnBerryPi_Pin.png', (_req, res) => {
  res.sendFile(path.join(brandingDir, 'LawnBerryPi_Pin.png'))
})

// IMPORTANT: Register more specific proxies BEFORE generic ones to avoid mismatches

// Proxy WebSocket for /api/v2/ws/telemetry as-is (frontend connects here by default)
app.use(
  '/api/v2/ws/telemetry',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: true,
  })
)

// Direct /api/v2 passthrough (must be before generic '/api')
app.use('/api/v2', (req, _res, next) => {
  console.log(`[proxy] match /api/v2 -> ${req.method} ${req.originalUrl}`)
  next()
})
app.use(
  '/api/v2',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: false,
    logLevel: 'debug',
    pathRewrite: (path) => '/api/v2' + path,
  })
)

// Proxy API to backend. Express strips the mount prefix '/api', so inside
// this middleware, `path` will start with '/v2/...' or '/something'.
// - If it's '/v2/...', prepend '/api' -> '/api/v2/...'
// - Else, prepend '/api/v2' -> '/api/v2/...'
app.use('/api', (req, _res, next) => {
  console.log(`[proxy] match /api -> ${req.method} ${req.originalUrl}`)
  next()
})
app.use(
  '/api',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: false,
    logLevel: 'debug',
    pathRewrite: (path) => {
      if (path.startsWith('/v2/')) return '/api' + path
      return '/api/v2' + path
    },
  })
)

// Proxy WebSocket path to backend telemetry endpoint
app.use(
  '/ws',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: true,
    pathRewrite: () => '/api/v2/ws/telemetry',
  })
)

// (kept earlier and more specific above)

// Serve static built files
const distDir = path.resolve(__dirname, 'dist')
app.use(express.static(distDir, { maxAge: '1d', index: 'index.html' }))

// SPA fallback: serve index.html for any non-API route
app.get('*', (req, res) => {
  // Avoid intercepting proxied routes
  if (req.path.startsWith('/api') || req.path.startsWith('/ws')) {
    return res.status(404).send('Not Found')
  }
  res.sendFile(path.join(distDir, 'index.html'))
})

app.listen(PORT, '0.0.0.0', () => {
  console.log(`LawnBerry frontend is running at http://0.0.0.0:${PORT}`)
  console.log(`Proxying API to ${BACKEND_URL}`)
})
