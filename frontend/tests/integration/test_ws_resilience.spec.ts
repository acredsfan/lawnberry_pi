import { describe, it, expect, vi } from 'vitest'
import { useWebSocket } from '../../src/composables/useWebSocket'

// Mock socket.io-client (define inside factory to avoid hoisting issues)
vi.mock('socket.io-client', () => {
  type Handler = (...args: unknown[]) => void
  class MockSocket {
    private handlers: Record<string, Handler[]> = {}
    connected = false
    // capture emitted events for assertions
    public emitted: Array<{ event: string; data: unknown }> = []
    on(event: string, handler: Handler) {
      this.handlers[event] = this.handlers[event] || []
      this.handlers[event].push(handler)
    }
    emit(event: string, data: unknown) {
      this.emitted.push({ event, data })
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
  return { io, Socket: MockSocket as any }
})

describe('useWebSocket resilience', () => {
  it('reconnects with backoff and resubscribes', async () => {
    vi.useFakeTimers()
    const ws = useWebSocket('/ws')

    // Subscribe and set cadence before connect
    ws.subscribeTopic('telemetry/updates')
    ws.setCadence(7)

    await ws.connect()
    ;(ws.socket.value as any).connect()
    expect(ws.isConnected.value).toBe(true)

    // Simulate disconnect
    ;(ws.socket.value as any).disconnect()
    expect(ws.isConnected.value).toBe(false)

    // Advance timers to trigger reconnect attempt
    vi.advanceTimersByTime(500)

    // Simulate new connection established after backoff
    const mock = ws.socket.value as any
    mock.connect()
    expect(ws.isConnected.value).toBe(true)

    // Assert resubscribe and cadence re-applied
    const emitted = (ws.socket.value as any).emitted as Array<{ event: string; data: any }>
    const subscribeEvents = emitted.filter((e) => e.event === 'subscribe')
    const cadenceEvents = emitted.filter((e) => e.event === 'set_cadence')
    expect(subscribeEvents.length).toBeGreaterThan(0)
    expect(cadenceEvents.length).toBeGreaterThan(0)
    expect(cadenceEvents.at(-1)?.data).toEqual({ cadence_hz: 7 })

    vi.useRealTimers()
  })
})
