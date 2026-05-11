import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'
import { useMissionStore } from '@/stores/mission'
import apiService from '@/services/api'

const mockedApi = apiService as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
  patch: ReturnType<typeof vi.fn>
  delete: ReturnType<typeof vi.fn>
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

      expect(store.statusDetail).toBe('Failed to pause mission')
    })

    it('clears statusDetail after a successful pause', async () => {
      const store = useMissionStore()
      setActiveMission(store, 'running')
      store.statusDetail = 'some previous error'
      mockedApi.post.mockResolvedValueOnce({ data: {} })

      await store.pauseCurrentMission()

      expect(store.statusDetail).toBe('Paused by operator')
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

      expect(store.statusDetail).toBe('Failed to resume mission')
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

describe('Mission Store — CRUD actions (fetchMissions / updateMissionById / deleteMissionById)', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  afterEach(() => {
    const instances = (globalThis as any).__wsMockInstances as Array<any>
    instances.length = 0
  })

  const sampleMission = {
    id: 'm1',
    name: 'Loop',
    waypoints: [{ id: 'w1', lat: 0.1, lon: 0.1, blade_on: false, speed: 50 }],
    created_at: '2025-01-01T00:00:00Z',
  }

  // ── fetchMissions ──────────────────────────────────────────────────────────

  it('fetchMissions populates missions from API', async () => {
    const store = useMissionStore()
    mockedApi.get.mockResolvedValueOnce({ data: [sampleMission] })

    await store.fetchMissions()

    expect(store.missions).toHaveLength(1)
    expect(store.missions[0].id).toBe('m1')
  })

  it('fetchMissions swallows errors and leaves missions unchanged', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    mockedApi.get.mockRejectedValueOnce(new Error('network error'))

    await store.fetchMissions()

    expect(store.missions).toHaveLength(1) // unchanged
  })

  // ── selectMission ────────────────────────────────────────────────────────

  it('selectMission sets waypoints from the mission', async () => {
    const store = useMissionStore()
    mockedApi.get.mockResolvedValueOnce({ data: { status: 'idle', mission_id: 'm1', completion_percentage: 0, total_waypoints: 1 } })

    await store.selectMission(sampleMission)

    expect(store.waypoints).toHaveLength(1)
    expect(store.waypoints[0].lat).toBeCloseTo(0.1)
    expect(store.currentMission?.id).toBe('m1')
  })

  // ── updateMissionById ────────────────────────────────────────────────────

  it('updateMissionById updates missions list with server response', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    const updated = { ...sampleMission, name: 'Renamed' }
    mockedApi.patch.mockResolvedValueOnce({ data: updated })

    await store.updateMissionById('m1', { name: 'Renamed' })

    expect(store.missions[0].name).toBe('Renamed')
  })

  it('updateMissionById also updates currentMission and waypoints when active', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    store.waypoints = [...sampleMission.waypoints]
    const newWaypoints = [{ id: 'w2', lat: 0.5, lon: 0.5, blade_on: true, speed: 80 }]
    const updated = { ...sampleMission, waypoints: newWaypoints }
    mockedApi.patch.mockResolvedValueOnce({ data: updated })

    await store.updateMissionById('m1', { waypoints: newWaypoints })

    expect(store.currentMission?.waypoints[0].lat).toBeCloseTo(0.5)
    expect(store.waypoints[0].lat).toBeCloseTo(0.5)
  })

  it('updateMissionById does not overwrite waypoints when payload has no waypoints', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    store.waypoints = [...sampleMission.waypoints]
    const updated = { ...sampleMission, name: 'Renamed' }
    mockedApi.patch.mockResolvedValueOnce({ data: updated })

    await store.updateMissionById('m1', { name: 'Renamed' })

    // waypoints unchanged because payload had no waypoints key
    expect(store.waypoints[0].lat).toBeCloseTo(0.1)
  })

  it('updateMissionById throws and sets statusDetail on error', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    mockedApi.patch.mockRejectedValueOnce(new Error('server error'))

    await expect(store.updateMissionById('m1', { name: 'X' })).rejects.toThrow()
    expect(store.statusDetail).toBe('server error')
  })

  // ── deleteMissionById ────────────────────────────────────────────────────

  it('deleteMissionById removes mission from list', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    mockedApi.delete.mockResolvedValueOnce({})

    await store.deleteMissionById('m1')

    expect(store.missions).toHaveLength(0)
  })

  it('deleteMissionById clears currentMission when it was the active one', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    store.waypoints = [...sampleMission.waypoints]
    store.missionStatus = 'completed'
    mockedApi.delete.mockResolvedValueOnce({})

    await store.deleteMissionById('m1')

    expect(store.currentMission).toBeNull()
    expect(store.waypoints).toHaveLength(0)
    expect(store.missionStatus).toBe('idle')
  })

  it('deleteMissionById does not touch currentMission when deleting a different mission', async () => {
    const store = useMissionStore()
    const other = { ...sampleMission, id: 'm2', name: 'Other' }
    store.missions = [sampleMission, other]
    store.currentMission = sampleMission
    mockedApi.delete.mockResolvedValueOnce({})

    await store.deleteMissionById('m2')

    expect(store.currentMission?.id).toBe('m1')
    expect(store.missions).toHaveLength(1)
  })

  it('deleteMissionById throws and sets statusDetail on error', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    mockedApi.delete.mockRejectedValueOnce(new Error('server error'))

    await expect(store.deleteMissionById('m1')).rejects.toThrow()
    expect(store.statusDetail).toBe('server error')
  })

  // ── WS handlers ──────────────────────────────────────────────────────────

  it('WS mission.deleted removes mission from list', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    // init() subscribes WS handlers
    mockedApi.get.mockResolvedValue({ data: [] }) // fetchMissions + possibly init fetch
    await store.init()

    const instances = (globalThis as any).__wsMockInstances as Array<any>
    const wsInst = instances[instances.length - 1].instance
    wsInst.__emit('mission.deleted', { mission_id: 'm1' })
    await flushPromises()

    expect(store.missions.find(m => m.id === 'm1')).toBeUndefined()
  })

  it('WS mission.deleted clears currentMission when it was active', async () => {
    const store = useMissionStore()
    store.missions = [sampleMission]
    store.currentMission = sampleMission
    store.waypoints = [...sampleMission.waypoints]
    mockedApi.get.mockResolvedValue({ data: [] })
    await store.init()

    const instances = (globalThis as any).__wsMockInstances as Array<any>
    const wsInst = instances[instances.length - 1].instance
    wsInst.__emit('mission.deleted', { mission_id: 'm1' })
    await flushPromises()

    expect(store.currentMission).toBeNull()
    expect(store.waypoints).toHaveLength(0)
  })
})
