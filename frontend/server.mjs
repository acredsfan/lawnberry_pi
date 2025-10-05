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

// Proxy API to backend, rewriting /api -> /api/v2
app.use(
  '/api',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: false,
    pathRewrite: (path) => `/api/v2${path}`,
  })
)

// Also proxy direct /api/v2 paths to backend (no rewrite) so clients can call /api/v2/* directly
app.use(
  '/api/v2',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: false,
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

// Proxy WebSocket for /api/v2/ws/telemetry as-is (frontend connects here by default)
app.use(
  '/api/v2/ws/telemetry',
  createProxyMiddleware({
    target: BACKEND_URL,
    changeOrigin: true,
    ws: true,
  })
)

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
