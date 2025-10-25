import { beforeEach, vi } from 'vitest'

class LocalStorageMock {
  private store = new Map<string, string>()

  clear() {
    this.store.clear()
  }

  getItem(key: string) {
    return this.store.has(key) ? this.store.get(key)! : null
  }

  setItem(key: string, value: string) {
    this.store.set(key, String(value))
  }

  removeItem(key: string) {
    this.store.delete(key)
  }
}

if (typeof globalThis.localStorage === 'undefined') {
  Object.defineProperty(globalThis, 'localStorage', {
    value: new LocalStorageMock(),
    configurable: true,
    enumerable: true,
    writable: true,
  })
}

const apiClient = {
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  patch: vi.fn(),
}

const sendControlCommand = vi.fn()
const getRoboHATStatus = vi.fn()
const getMapConfiguration = vi.fn()
const saveMapConfiguration = vi.fn()
const triggerMapProviderFallback = vi.fn()

vi.mock('@/services/api', () => ({
  __esModule: true,
  default: apiClient,
  useApiService: () => apiClient,
  sendControlCommand,
  getRoboHATStatus,
  getMapConfiguration,
  saveMapConfiguration,
  triggerMapProviderFallback,
}))

type TopicCallbackEntry = {
  callback: (data: any) => void
  unsubscribe: ReturnType<typeof vi.fn>
}

const wsInstances: Array<{
  type: string
  handlers?: { onMessage?: (msg: any) => void }
  instance: any
  topicCallbacks: Map<string, TopicCallbackEntry[]>
}> = []

const useWebSocketMock = vi.fn((type: 'telemetry' | 'control' = 'telemetry', handlers?: { onMessage?: (msg: any) => void }) => {
  const topicCallbacks = new Map<string, TopicCallbackEntry[]>()

  const instance = {
    connected: { value: false },
    connecting: { value: false },
    connect: vi.fn().mockResolvedValue(undefined),
    disconnect: vi.fn(),
    subscribe: vi.fn((topic: string, callback: (data: any) => void) => {
      const existing = topicCallbacks.get(topic) ?? []
      const unsubscribe = vi.fn(() => {
        const arr = topicCallbacks.get(topic)
        if (!arr) return
        const idx = arr.findIndex(entry => entry.callback === callback)
        if (idx >= 0) {
          arr.splice(idx, 1)
        }
        if (arr.length === 0) {
          topicCallbacks.delete(topic)
        }
      })

      existing.push({ callback, unsubscribe })
      topicCallbacks.set(topic, existing)
      return unsubscribe
    }),
    unsubscribe: vi.fn((topic: string, callback?: (data: any) => void) => {
      if (!callback) {
        topicCallbacks.delete(topic)
        return
      }
      const arr = topicCallbacks.get(topic)
      if (!arr) {
        return
      }
      const entry = arr.find(item => item.callback === callback)
      if (entry) {
        entry.unsubscribe()
      }
      if (topicCallbacks.get(topic)?.length === 0) {
        topicCallbacks.delete(topic)
      }
    }),
    setCadence: vi.fn(),
    ping: vi.fn(),
    listTopics: vi.fn(),
    dispatchTestMessage: vi.fn((message: any) => {
      handlers?.onMessage?.(message)
      if (message?.topic) {
        const callbacks = topicCallbacks.get(message.topic)
        callbacks?.forEach(entry => entry.callback(message.data ?? message))
      }
    }),
    __emit(topic: string, payload: any) {
      const callbacks = topicCallbacks.get(topic)
      callbacks?.forEach(entry => entry.callback(payload))
    },
  }

  wsInstances.push({ type, handlers, instance, topicCallbacks })
  return instance
})

vi.mock('@/services/websocket', () => ({
  __esModule: true,
  useWebSocket: useWebSocketMock,
}))

Object.defineProperty(globalThis, '__wsMockInstances', {
  value: wsInstances,
  configurable: true,
  enumerable: false,
  writable: false,
})

beforeEach(() => {
  apiClient.get.mockReset()
  apiClient.post.mockReset()
  apiClient.put.mockReset()
  apiClient.delete.mockReset()
  apiClient.patch.mockReset()
  sendControlCommand.mockReset()
  getRoboHATStatus.mockReset()
  getMapConfiguration.mockReset()
  saveMapConfiguration.mockReset()
  triggerMapProviderFallback.mockReset()
  useWebSocketMock.mockClear()
  localStorage.clear()
})
