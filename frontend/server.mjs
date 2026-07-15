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
import { isIP } from 'node:net'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const app = express()
const PORT = process.env.PORT || 3000
const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8081'

function shouldCompress(req, res) {
  if (req.path === '/api/v2/camera/stream.mjpeg' || req.path === '/api/v2/camera/frame') {
    return false
  }
  return compression.filter(req, res)
}

// Logging & compression
app.use(morgan('combined'))
app.use(compression({ filter: shouldCompress }))

function normalizeIp(value) {
  const candidate = String(value || '').trim().replace(/^::ffff:/, '')
  return isIP(candidate) ? candidate : null
}

function isLoopback(value) {
  const normalized = normalizeIp(value)
  return normalized === '127.0.0.1' || normalized === '::1'
}

// The frontend is the only production HTTP hop to Uvicorn. Replace all
// browser-controlled forwarding identity with one canonical address. A
// Cloudflare client address is accepted only when the immediate TCP peer is
// loopback (the local cloudflared process); direct LAN callers use their socket
// address even if they spoof Cloudflare or forwarding headers.
app.use((req, _res, next) => {
  const peerIp = normalizeIp(req.socket.remoteAddress)
  const cloudflareIp = normalizeIp(req.headers['cf-connecting-ip'])
  const reverseProxyIp = normalizeIp(req.headers['x-real-ip'])
  delete req.headers['x-forwarded-for']
  delete req.headers['forwarded']
  delete req.headers['x-real-ip']
  delete req.headers['x-lawnberry-client-ip']
  const trustedUpstreamIp = cloudflareIp || reverseProxyIp
  const clientIp = isLoopback(peerIp) && trustedUpstreamIp ? trustedUpstreamIp : peerIp
  if (clientIp) req.headers['x-lawnberry-client-ip'] = clientIp
  next()
})

// Serve branding assets (e.g., LawnBerryPi_Pin.png) so they are available to the UI
const brandingDir = path.resolve(__dirname, '../branding')
app.use('/branding', express.static(brandingDir, { maxAge: '30d' }))
// Back-compat: expose the primary mower pin at the root path expected by the editor
app.get('/LawnBerryPi_Pin.png', (_req, res) => {
  res.sendFile(path.join(brandingDir, 'LawnBerryPi_Pin.png'))
})

// IMPORTANT: Register more specific proxies BEFORE generic ones to avoid mismatches

// Proxy authenticated WebSocket channels as-is. The browser sends its signed
// LawnBerry JWT in Sec-WebSocket-Protocol, which http-proxy-middleware forwards
// without putting credentials in the URL or access log.
for (const channel of ['telemetry', 'control']) {
  app.use(
    `/api/v2/ws/${channel}`,
    createProxyMiddleware({
      target: BACKEND_URL,
      changeOrigin: true,
      ws: true,
    })
  )
}

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
