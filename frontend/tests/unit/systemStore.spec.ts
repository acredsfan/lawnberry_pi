import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'

const mocks = vi.hoisted(() => ({
  apiGet: vi.fn(),
  topicHandlers: new Map<string, (data: unknown) => void>(),
  setConnected: (_value: boolean) => {},
}))

vi.mock('@/services/api', () => ({
  default: {
    get: mocks.apiGet,
    getTelemetryStream: vi.fn(),
    exportTelemetryDiagnostic: vi.fn(),
    pingTelemetry: vi.fn(),
  },
}))

vi.mock('@/services/websocket', async () => {
  const { ref } = await import('vue')
  const connected = ref(false)
  mocks.setConnected = (value: boolean) => {
    connected.value = value
  }
  return {
    useWebSocket: () => ({
      connected,
      connecting: ref(false),
      connect: vi.fn(async () => {
        connected.value = true
      }),
      disconnect: vi.fn(async () => {
        connected.value = false
      }),
      subscribe: vi.fn((topic: string, handler: (data: unknown) => void) => {
        mocks.topicHandlers.set(topic, handler)
      }),
      unsubscribe: vi.fn(),
    }),
  }
})

import { useSystemStore } from '@/stores/system'

describe('system store runtime truth', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-07-15T12:00:00Z'))
    setActivePinia(createPinia())
    mocks.setConnected(false)
    mocks.topicHandlers.clear()
    mocks.apiGet.mockReset().mockResolvedValue({
      data: {
        version: '2.0.0',
        commit_sha: 'a'.repeat(40),
        short_sha: 'a'.repeat(12),
        source: 'environment',
        started_at: '2026-07-15T11:00:00Z',
      },
    })
  })

  it('tracks live connection changes, build SHA, and telemetry staleness', async () => {
    const store = useSystemStore()
    await store.initialize()

    expect(store.connectionStatus).toBe('connected')
    expect(store.buildInfo?.short_sha).toBe('a'.repeat(12))

    mocks.topicHandlers.get('telemetry.system')?.({
      safety_state: 'nominal',
      source: 'hardware',
      sample: {
        source: 'hardware',
        observed_at: '2026-07-15T12:00:00Z',
        fresh: true,
      },
    })
    expect(store.telemetryFresh).toBe(true)
    expect(store.effectiveStatus).toBe('active')

    mocks.setConnected(false)
    await nextTick()
    expect(store.connectionStatus).toBe('disconnected')

    vi.advanceTimersByTime(6_000)
    expect(store.telemetryFresh).toBe(false)
    expect(store.effectiveStatus).toBe('unknown')
    await store.shutdown()
  })
})
