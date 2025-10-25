import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useControlStore } from '@/stores/control'
import * as api from '@/services/api'

function getControlWsEntry() {
  const instances = (globalThis as any).__wsMockInstances as Array<{
    type: string
    handlers?: { onMessage?: (msg: any) => void }
    instance: any
    topicCallbacks: any
  }>
  for (let i = instances.length - 1; i >= 0; i -= 1) {
    const candidate = instances[i]
    if (candidate.type === 'control') {
      return candidate
    }
  }
  throw new Error('Control WebSocket mock was not initialized')
}

function createStoreWithWs() {
  const store = useControlStore()
  const wsEntry = getControlWsEntry()
  wsEntry.instance.subscribe.mockClear()
  wsEntry.instance.unsubscribe.mockClear()
  wsEntry.instance.connect.mockClear()
  wsEntry.instance.disconnect.mockClear()
  wsEntry.instance.dispatchTestMessage?.mockClear?.()
  wsEntry.topicCallbacks.clear()
  store.initWebSocket()
  return { store, wsEntry }
}

describe('Control Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    const instances = (globalThis as any).__wsMockInstances as Array<any>
    instances.length = 0
  })

  describe('initialization', () => {
    it('initializes with correct default state', () => {
      const { store } = createStoreWithWs()

      expect(store.lockoutActive).toBe(false)
      expect(store.lockoutReason).toBe('')
      expect(store.lockoutUntil).toBeNull()
      expect(store.robohatStatus).toBeNull()
      expect(store.lastCommandEcho).toBeNull()
      expect(store.commandInProgress).toBe(false)
      expect(store.remediationLink).toBe('')
    })
  })

  describe('submitCommand', () => {
    it('submits command successfully when not locked out', async () => {
      const { store } = createStoreWithWs()
      const mockResponse = {
        command_id: 'cmd123',
        status: 'accepted',
        timestamp: new Date().toISOString(),
      }

      vi.mocked(api.sendControlCommand).mockResolvedValue(mockResponse)

      await store.submitCommand('FORWARD', { speed: 50 })

      expect(store.commandInProgress).toBe(false)
      expect(store.lastCommandEcho).toEqual(mockResponse)
      expect(api.sendControlCommand).toHaveBeenCalledWith('FORWARD', { speed: 50 })
    })

    it('prevents command submission during lockout', async () => {
      const { store } = createStoreWithWs()
      store.lockoutActive = true
      store.lockoutReason = 'Emergency stop activated'

      await expect(store.submitCommand('FORWARD', {})).rejects.toThrow(
        'Control locked out: Emergency stop activated'
      )

      expect(api.sendControlCommand).not.toHaveBeenCalled()
    })

    it('handles command submission errors', async () => {
      const { store } = createStoreWithWs()
      const error = new Error('Communication failure')

      vi.mocked(api.sendControlCommand).mockRejectedValue(error)

      await expect(store.submitCommand('FORWARD', {})).rejects.toThrow('Communication failure')
      expect(store.commandInProgress).toBe(false)
    })

    it('sets commandInProgress flag during submission', async () => {
      const { store } = createStoreWithWs()
      let progressDuringCall = false

      vi.mocked(api.sendControlCommand).mockImplementation(async () => {
        progressDuringCall = store.commandInProgress
        return {
          command_id: 'cmd123',
          status: 'accepted',
          timestamp: new Date().toISOString(),
        }
      })

      await store.submitCommand('STOP', {})

      expect(progressDuringCall).toBe(true)
      expect(store.commandInProgress).toBe(false)
    })
  })

  describe('fetchRoboHATStatus', () => {
    it('fetches and stores RoboHAT status', async () => {
      const { store } = createStoreWithWs()
      const mockStatus = {
        connected: true,
        firmware_version: 'v1.2.3',
        last_heartbeat: new Date().toISOString(),
        motor_states: {
          left: 'idle',
          right: 'idle',
        },
      }

      vi.mocked(api.getRoboHATStatus).mockResolvedValue(mockStatus)

      await store.fetchRoboHATStatus()

      expect(store.robohatStatus).toEqual(mockStatus)
      expect(api.getRoboHATStatus).toHaveBeenCalled()
    })

    it('handles status fetch errors gracefully', async () => {
      const { store } = createStoreWithWs()
      const error = new Error('Connection timeout')

      vi.mocked(api.getRoboHATStatus).mockRejectedValue(error)

      await expect(store.fetchRoboHATStatus()).rejects.toThrow('Connection timeout')
      expect(store.robohatStatus).toBeNull()
    })
  })

  describe('WebSocket integration', () => {
    it('subscribes to control WebSocket on initialization', () => {
      const { store, wsEntry } = createStoreWithWs()

      expect(wsEntry.instance.subscribe).toHaveBeenCalledWith('control', expect.any(Function))
    })

    it('handles command echo messages from WebSocket', () => {
      const { store, wsEntry } = createStoreWithWs()
      const echoMessage = {
        type: 'command_echo',
        payload: {
          command_id: 'cmd123',
          command: 'FORWARD',
          status: 'executed',
          timestamp: new Date().toISOString(),
        },
      }

      wsEntry.handlers?.onMessage?.(echoMessage)

      expect(store.lastCommandEcho).toEqual(echoMessage.payload)
    })

    it('handles lockout messages from WebSocket', () => {
      const { store, wsEntry } = createStoreWithWs()
      const lockoutMessage = {
        type: 'lockout',
        active: true,
        reason: 'Low battery',
        until: new Date(Date.now() + 30000).toISOString(),
        remediation_link: '/docs/troubleshooting#low-battery',
      }

      wsEntry.handlers?.onMessage?.(lockoutMessage)

      expect(store.lockoutActive).toBe(true)
      expect(store.lockoutReason).toBe('Low battery')
      expect(store.lockoutUntil).toBe(lockoutMessage.until)
      expect(store.remediationLink).toBe('/docs/troubleshooting#low-battery')
    })

    it('clears lockout when receiving unlock message', () => {
      const { store, wsEntry } = createStoreWithWs()
      store.lockoutActive = true
      store.lockoutReason = 'Test lockout'
      store.lockoutUntil = new Date().toISOString()
      store.remediationLink = '/docs/test'

      const unlockMessage = {
        type: 'unlock',
        reason: '',
        until: null,
        remediation_link: '',
      }

      wsEntry.handlers?.onMessage?.(unlockMessage)

      expect(store.lockoutActive).toBe(false)
      expect(store.lockoutReason).toBe('')
      expect(store.lockoutUntil).toBeNull()
      expect(store.remediationLink).toBe('')
    })
  })

  describe('computed properties', () => {
    it('canSubmitCommand returns false during lockout', () => {
      const { store } = createStoreWithWs()
      store.lockoutActive = true

      expect(store.canSubmitCommand).toBe(false)
    })

    it('canSubmitCommand returns false during command in progress', () => {
      const { store } = createStoreWithWs()
      store.commandInProgress = true

      expect(store.canSubmitCommand).toBe(false)
    })

    it('canSubmitCommand returns true when available', () => {
      const { store } = createStoreWithWs()
      store.lockoutActive = false
      store.commandInProgress = false

      expect(store.canSubmitCommand).toBe(true)
    })

    it('lockoutTimeRemaining calculates remaining time correctly', () => {
      const { store } = createStoreWithWs()
      const futureTime = new Date(Date.now() + 5000)
      store.lockoutUntil = futureTime.toISOString()

      const remaining = store.lockoutTimeRemaining

      expect(remaining).toBeGreaterThan(0)
      expect(remaining).toBeLessThanOrEqual(5000)
    })

    it('lockoutTimeRemaining returns 0 when no lockout', () => {
      const { store } = createStoreWithWs()
      store.lockoutUntil = null

      expect(store.lockoutTimeRemaining).toBe(0)
    })
  })

  describe('cleanup', () => {
    it('unsubscribes from WebSocket on cleanup', () => {
      const { store, wsEntry } = createStoreWithWs()
      const callbacks = wsEntry.topicCallbacks.get('control') as any[] | undefined
      expect(callbacks).toBeDefined()
      expect((callbacks?.length ?? 0)).toBeGreaterThan(0)
      const unsubscribeSpy = callbacks![0]?.unsubscribe

      store.cleanup()

      expect(unsubscribeSpy).toHaveBeenCalled()
    })
  })
})
