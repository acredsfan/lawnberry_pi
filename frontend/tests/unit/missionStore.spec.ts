import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useMissionStore } from '@/stores/mission'
import apiService from '@/services/api'

const mockedApi = apiService as unknown as {
  post: ReturnType<typeof vi.fn>
}

/** Puts the store into a "mission running" state so pause/resume guards pass. */
function setActiveMission(store: ReturnType<typeof useMissionStore>, status: 'running' | 'paused' = 'running') {
  store.currentMission = {
    id: 'mission-123',
    name: 'Test Mission',
    waypoints: [],
    created_at: '2025-01-01T00:00:00Z',
  }
  store.missionStatus = status
}

describe('Mission Store — optimistic mutation guard (ARCH-008)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    // Clear ws mock instances so they don't bleed between tests
    const instances = (globalThis as any).__wsMockInstances as Array<any>
    instances.length = 0
  })

  // ─────────────────────────────────────────────────────────────────────────
  // pauseCurrentMission
  // ─────────────────────────────────────────────────────────────────────────
  describe('pauseCurrentMission', () => {
    it('sets missionStatus to "paused" after a successful API call', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'running')
      mockedApi.post.mockResolvedValueOnce({ data: {} })

      await store.pauseCurrentMission()

      expect(store.missionStatus).toBe('paused')
    })

    it('does NOT change missionStatus when the API call fails', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'running')
      mockedApi.post.mockRejectedValueOnce(new Error('Network error'))

      // Must NOT throw — error should be absorbed and surfaced via statusDetail
      await store.pauseCurrentMission()

      expect(store.missionStatus).toBe('running')
    })

    it('sets statusDetail to an error message when the API call fails', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'running')
      mockedApi.post.mockRejectedValueOnce(new Error('Network error'))

      await store.pauseCurrentMission()

      expect(store.statusDetail).toBeTruthy()
      expect(typeof store.statusDetail).toBe('string')
    })

    it('clears statusDetail after a successful pause', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'running')
      store.statusDetail = 'some previous error'
      mockedApi.post.mockResolvedValueOnce({ data: {} })

      await store.pauseCurrentMission()

      // statusDetail should be reset (null or an operator-facing message — not an error)
      expect(store.statusDetail).not.toContain('Failed')
    })

    it('does nothing when there is no active mission', async () => {
      const store = useMissionStore()
      store.currentMission = null
      store.missionStatus = 'idle'

      await store.pauseCurrentMission()

      expect(mockedApi.post).not.toHaveBeenCalled()
      expect(store.missionStatus).toBe('idle')
    })
  })

  // ─────────────────────────────────────────────────────────────────────────
  // resumeCurrentMission
  // ─────────────────────────────────────────────────────────────────────────
  describe('resumeCurrentMission', () => {
    it('sets missionStatus to "running" after a successful API call', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'paused')
      mockedApi.post.mockResolvedValueOnce({ data: {} })

      await store.resumeCurrentMission()

      expect(store.missionStatus).toBe('running')
    })

    it('does NOT change missionStatus when the API call fails', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'paused')
      mockedApi.post.mockRejectedValueOnce(new Error('Network error'))

      // Must NOT throw — error should be absorbed and surfaced via statusDetail
      await store.resumeCurrentMission()

      expect(store.missionStatus).toBe('paused')
    })

    it('sets statusDetail to an error message when the API call fails', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'paused')
      mockedApi.post.mockRejectedValueOnce(new Error('Network error'))

      await store.resumeCurrentMission()

      expect(store.statusDetail).toBeTruthy()
      expect(typeof store.statusDetail).toBe('string')
    })

    it('clears statusDetail after a successful resume', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'paused')
      store.statusDetail = 'some previous error'
      mockedApi.post.mockResolvedValueOnce({ data: {} })

      await store.resumeCurrentMission()

      expect(store.statusDetail).toBeNull()
    })

    it('does nothing when there is no active mission', async () => {
      const store = useMissionStore()
      store.currentMission = null
      store.missionStatus = 'idle'

      await store.resumeCurrentMission()

      expect(mockedApi.post).not.toHaveBeenCalled()
      expect(store.missionStatus).toBe('idle')
    })
  })

  // ─────────────────────────────────────────────────────────────────────────
  // abortCurrentMission — verify already-correct behaviour is preserved
  // ─────────────────────────────────────────────────────────────────────────
  describe('abortCurrentMission (pre-existing correct behaviour)', () => {
    it('sets missionStatus to "aborted" after a successful API call', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'running')
      mockedApi.post.mockResolvedValueOnce({ data: {} })

      await store.abortCurrentMission()

      expect(store.missionStatus).toBe('aborted')
    })

    it('clears currentMission after a successful abort', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'running')
      mockedApi.post.mockResolvedValueOnce({ data: {} })

      await store.abortCurrentMission()

      expect(store.currentMission).toBeNull()
    })
  })

  // ─────────────────────────────────────────────────────────────────────────
  // startCurrentMission — verify already-correct behaviour is preserved
  // ─────────────────────────────────────────────────────────────────────────
  describe('startCurrentMission (pre-existing correct behaviour)', () => {
    it('sets missionStatus to "running" after a successful API call', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'idle')
      mockedApi.post.mockResolvedValueOnce({ data: {} })

      await store.startCurrentMission()

      expect(store.missionStatus).toBe('running')
    })
  })
})
