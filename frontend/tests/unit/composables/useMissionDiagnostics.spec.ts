import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { useMissionDiagnostics } from '@/composables/useMissionDiagnostics'

const mockConnect = vi.fn().mockResolvedValue(undefined)
const mockSubscribe = vi.fn()
const mockUnsubscribe = vi.fn()
const mockDisconnect = vi.fn()

vi.mock('@/services/websocket', () => ({
  useWebSocket: vi.fn(() => ({
    connect: mockConnect,
    subscribe: mockSubscribe,
    unsubscribe: mockUnsubscribe,
    disconnect: mockDisconnect,
  })),
}))

async function mountWithComposable() {
  let result: ReturnType<typeof useMissionDiagnostics>
  const Wrapper = defineComponent({
    setup() { result = useMissionDiagnostics(); return {} },
    template: '<div />',
  })
  const wrapper = mount(Wrapper)
  // flush so the async onMounted (await connect then subscribe) settles
  await flushPromises()
  return { wrapper, getResult: () => result! }
}

describe('useMissionDiagnostics', () => {
  beforeEach(() => vi.clearAllMocks())

  it('initializes with null diagnostics', async () => {
    const { getResult } = await mountWithComposable()
    expect(getResult().diagnostics.value).toBeNull()
  })

  it('updates diagnostics when valid payload arrives', async () => {
    const { getResult } = await mountWithComposable()
    const callback = mockSubscribe.mock.calls[0]?.[1]
    expect(callback).toBeDefined()
    const payload = {
      run_id: 'abc123',
      mission_id: 'mission-1',
      blocked_command_count: 2,
      average_pose_quality: 'gps_float',
      heading_alignment_samples: 5,
      pose_update_count: 100,
    }
    callback(payload)
    expect(getResult().diagnostics.value).toEqual(payload)
  })

  it('ignores payloads without run_id', async () => {
    const { getResult } = await mountWithComposable()
    const callback = mockSubscribe.mock.calls[0]?.[1]
    callback({ mission_id: 'x' }) // no run_id
    expect(getResult().diagnostics.value).toBeNull()
  })

  it('unsubscribes on unmount without disconnecting the shared singleton', async () => {
    const { wrapper } = await mountWithComposable()
    await wrapper.unmount()
    expect(mockUnsubscribe).toHaveBeenCalledWith('mission.diagnostics', expect.any(Function))
    expect(mockDisconnect).not.toHaveBeenCalled()
  })
})
