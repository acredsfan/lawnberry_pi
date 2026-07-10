import { describe, it, expect, vi, afterEach } from 'vitest'

class MockWebSocket {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 3
  static instances: MockWebSocket[] = []

  readyState = MockWebSocket.CONNECTING
  sent: string[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: ((event: Event) => void) | null = null

  constructor(public url: string) {
    MockWebSocket.instances.push(this)
  }

  send(data: string) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }

  open() {
    this.readyState = MockWebSocket.OPEN
    this.onopen?.()
  }
}

describe('WebSocketService resilience', () => {
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
    MockWebSocket.instances = []
  })

  it('reconnects with capped backoff and resubscribes through the native WebSocket path', async () => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    vi.stubGlobal('WebSocket', MockWebSocket)

    const { WebSocketService } = await vi.importActual<typeof import('../../src/services/websocket')>(
      '../../src/services/websocket'
    )
    const service = new WebSocketService('ws://localhost/api/v2/ws/telemetry')
    service.onTopic('telemetry/updates', vi.fn())

    const firstConnect = service.connect()
    const firstSocket = MockWebSocket.instances[0]
    firstSocket.open()
    await firstConnect

    expect(service.isConnected).toBe(true)
    expect(firstSocket.sent.map(JSON.parse)).toEqual([
      { type: 'subscribe', topic: 'telemetry/updates' },
      { type: 'set_cadence', cadence_hz: 5 },
    ])

    firstSocket.close()
    expect(service.isConnected).toBe(false)

    await vi.advanceTimersByTimeAsync(1000)
    const secondSocket = MockWebSocket.instances[1]
    secondSocket.open()
    await Promise.resolve()

    expect(service.isConnected).toBe(true)
    expect(secondSocket.sent.map(JSON.parse)).toEqual([
      { type: 'subscribe', topic: 'telemetry/updates' },
      { type: 'set_cadence', cadence_hz: 5 },
    ])
  })
})
