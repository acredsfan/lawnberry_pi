import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useControlStore } from '@/stores/control'
import * as api from '@/services/api'
import { useWebSocket } from '@/services/websocket'

// Mock the API service
vi.mock('@/services/api')

// Mock the WebSocket service
vi.mock('@/services/websocket', () => ({
  useWebSocket: vi.fn(() => ({
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    isConnected: { value: true },
  })),
}))

describe('Control Store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  describe('initialization', () => {
    it('initializes with correct default state', () => {
      const store = useControlStore()

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
      const store = useControlStore()
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
      const store = useControlStore()
      store.lockoutActive = true
      store.lockoutReason = 'Emergency stop activated'

      await expect(store.submitCommand('FORWARD', {})).rejects.toThrow(
        'Control locked out: Emergency stop activated'
      )

      expect(api.sendControlCommand).not.toHaveBeenCalled()
    })

    it('handles command submission errors', async () => {
      const store = useControlStore()
      const error = new Error('Communication failure')

      vi.mocked(api.sendControlCommand).mockRejectedValue(error)

      await expect(store.submitCommand('FORWARD', {})).rejects.toThrow('Communication failure')
      expect(store.commandInProgress).toBe(false)
    })

    it('sets commandInProgress flag during submission', async () => {
      const store = useControlStore()
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
      const store = useControlStore()
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
      const store = useControlStore()
      const error = new Error('Connection timeout')

      vi.mocked(api.getRoboHATStatus).mockRejectedValue(error)

      await expect(store.fetchRoboHATStatus()).rejects.toThrow('Connection timeout')
      expect(store.robohatStatus).toBeNull()
    })
  })

  describe('WebSocket integration', () => {
    it('subscribes to control WebSocket on initialization', () => {
      const mockSubscribe = vi.fn()
      vi.mocked(useWebSocket).mockReturnValue({
        subscribe: mockSubscribe,
        unsubscribe: vi.fn(),
        isConnected: { value: true },
      })

      const store = useControlStore()
      store.initWebSocket()

      expect(mockSubscribe).toHaveBeenCalledWith('control', expect.any(Function))
    })

    it('handles command echo messages from WebSocket', () => {
      const store = useControlStore()
      const mockCallback = vi.fn()

      vi.mocked(useWebSocket).mockReturnValue({
        subscribe: (topic: string, callback: (data: any) => void) => {
          mockCallback.mockImplementation(callback)
          return vi.fn()
        },
        unsubscribe: vi.fn(),
        isConnected: { value: true },
      })

      store.initWebSocket()

      const echoMessage = {
        type: 'command_echo',
        command_id: 'cmd123',
        command: 'FORWARD',
        status: 'executed',
        timestamp: new Date().toISOString(),
      }

      mockCallback(echoMessage)

      expect(store.lastCommandEcho).toEqual(echoMessage)
    })

    it('handles lockout messages from WebSocket', () => {
      const store = useControlStore()
      const mockCallback = vi.fn()

      vi.mocked(useWebSocket).mockReturnValue({
        subscribe: (topic: string, callback: (data: any) => void) => {
          mockCallback.mockImplementation(callback)
          return vi.fn()
        },
        unsubscribe: vi.fn(),
        isConnected: { value: true },
      })

      store.initWebSocket()

      const lockoutMessage = {
        type: 'lockout',
        active: true,
        reason: 'Low battery',
        until: new Date(Date.now() + 30000).toISOString(),
        remediation_link: '/docs/troubleshooting#low-battery',
      }

      mockCallback(lockoutMessage)

      expect(store.lockoutActive).toBe(true)
      expect(store.lockoutReason).toBe('Low battery')
      expect(store.lockoutUntil).toBe(lockoutMessage.until)
      expect(store.remediationLink).toBe('/docs/troubleshooting#low-battery')
    })

    it('clears lockout when receiving unlock message', () => {
      const store = useControlStore()
      store.lockoutActive = true
      store.lockoutReason = 'Test lockout'
      store.lockoutUntil = new Date().toISOString()
      store.remediationLink = '/docs/test'

      const mockCallback = vi.fn()

      vi.mocked(useWebSocket).mockReturnValue({
        subscribe: (topic: string, callback: (data: any) => void) => {
          mockCallback.mockImplementation(callback)
          return vi.fn()
        },
        unsubscribe: vi.fn(),
        isConnected: { value: true },
      })

      store.initWebSocket()

      const unlockMessage = {
        type: 'lockout',
        active: false,
        reason: '',
        until: null,
        remediation_link: '',
      }

      mockCallback(unlockMessage)

      expect(store.lockoutActive).toBe(false)
      expect(store.lockoutReason).toBe('')
      expect(store.lockoutUntil).toBeNull()
      expect(store.remediationLink).toBe('')
    })
  })

  describe('computed properties', () => {
    it('canSubmitCommand returns false during lockout', () => {
      const store = useControlStore()
      store.lockoutActive = true

      expect(store.canSubmitCommand).toBe(false)
    })

    it('canSubmitCommand returns false during command in progress', () => {
      const store = useControlStore()
      store.commandInProgress = true

      expect(store.canSubmitCommand).toBe(false)
    })

    it('canSubmitCommand returns true when available', () => {
      const store = useControlStore()
      store.lockoutActive = false
      store.commandInProgress = false

      expect(store.canSubmitCommand).toBe(true)
    })

    it('lockoutTimeRemaining calculates remaining time correctly', () => {
      const store = useControlStore()
      const futureTime = new Date(Date.now() + 5000)
      store.lockoutUntil = futureTime.toISOString()

      const remaining = store.lockoutTimeRemaining

      expect(remaining).toBeGreaterThan(0)
      expect(remaining).toBeLessThanOrEqual(5000)
    })

    it('lockoutTimeRemaining returns 0 when no lockout', () => {
      const store = useControlStore()
      store.lockoutUntil = null

      expect(store.lockoutTimeRemaining).toBe(0)
    })
  })

  describe('cleanup', () => {
    it('unsubscribes from WebSocket on cleanup', () => {
      const mockUnsubscribe = vi.fn()

      vi.mocked(useWebSocket).mockReturnValue({
        subscribe: vi.fn(() => mockUnsubscribe),
        unsubscribe: vi.fn(),
        isConnected: { value: true },
      })

      const store = useControlStore()
      store.initWebSocket()
      store.cleanup()

      expect(mockUnsubscribe).toHaveBeenCalled()
    })
  })
})
