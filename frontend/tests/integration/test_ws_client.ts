import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { useWebSocket } from '../../src/composables/useWebSocket'

// Mock socket.io-client io() and Socket
vi.mock('socket.io-client', () => {
  type Handler = (...args: unknown[]) => void
  class MockSocket {
    private handlers: Record<string, Handler[]> = {}
    connected = false
    constructor() {}
    on(event: string, handler: Handler) {
      this.handlers[event] = this.handlers[event] || []
      this.handlers[event].push(handler)
    }
    off(event: string, handler?: Handler) {
      if (!this.handlers[event]) return
      if (!handler) {
        delete this.handlers[event]
      } else {
        this.handlers[event] = this.handlers[event].filter((h) => h !== handler)
      }
    }
    emit(event: string, data: unknown) {
      // Loop back for testing specific events
      if (event === 'telemetry') this.trigger('telemetry', data)
      if (event === 'system_status') this.trigger('system_status', data)
      if (event === 'set_cadence') this.trigger('set_cadence', data)
    }
    connect() {
      this.connected = true
      this.trigger('connect')
    }
    disconnect() {
      this.connected = false
      this.trigger('disconnect', 'test-disconnect')
    }
    trigger(event: string, ...args: unknown[]) {
      (this.handlers[event] || []).forEach((h) => h(...args))
    }
  }
  const io = () => new MockSocket() as unknown as MockSocket
  return { io, Socket: MockSocket }
})

describe('useWebSocket composable', () => {
  beforeEach(() => {
    localStorage.clear()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('connects and updates isConnected', async () => {
    const ws = useWebSocket('/ws')
    await ws.connect()
    // simulate connect by calling internal mock connect
    ws.socket.value?.connect?.()
    expect(ws.isConnected.value).toBe(true)
  })

  it('emits events and receives telemetry loopback', async () => {
    const ws = useWebSocket('/ws')
    await ws.connect()
    ws.socket.value?.connect?.()
    ws.subscribe('telemetry', (payload: unknown) => {
      const p = payload as { battery?: { percentage?: number } }
      ws.lastMessage.value = { type: 'telemetry', ...p }
    })
    ws.emit('telemetry', { battery: { percentage: 50 } })
    expect(ws.lastMessage.value?.type).toBe('telemetry')
    const msg = ws.lastMessage.value as unknown
    if (
      typeof msg === 'object' &&
      msg !== null &&
      'battery' in (msg as Record<string, unknown>) &&
      typeof (msg as any).battery === 'object' &&
      (msg as any).battery !== null
    ) {
      expect(((msg as any).battery as { percentage: number }).percentage).toBe(50)
    } else {
      throw new Error('battery not present in telemetry message')
    }
  })

  it('provides setCadence helper that emits correct envelope', async () => {
    const ws = useWebSocket('/ws')
    await ws.connect()
    ws.socket.value?.connect?.()
    const spy = vi.spyOn(ws as unknown as { emit: (event: string, data: unknown) => void }, 'emit')
    ws.setCadence(8)
    expect(spy).toHaveBeenCalledWith('set_cadence', { cadence_hz: 8 })
  })
})
