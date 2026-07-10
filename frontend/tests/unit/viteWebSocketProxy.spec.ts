// @vitest-environment node

import { describe, expect, it } from 'vitest'
import config from '../../vite.config'

describe('Vite API WebSocket proxy (SPEC T8)', () => {
  it('keeps /api proxy websocket upgrades enabled for Cloudflare tunnel traffic', () => {
    const proxy = config.server?.proxy as Record<string, any>
    const apiProxy = proxy?.['/api']

    expect(apiProxy).toBeTruthy()
    expect(apiProxy.target).toBe('http://127.0.0.1:8081')
    expect(apiProxy.changeOrigin).toBe(true)
    expect(apiProxy.ws).toBe(true)
    expect('/api/v2/ws/telemetry'.startsWith('/api')).toBe(true)
  })
})
