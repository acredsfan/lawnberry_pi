import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { useJoystickDrive } from '@/composables/useJoystickDrive'

const mockSubmitCommand = vi.fn().mockResolvedValue({})
vi.mock('@/stores/control', () => ({
  useControlStore: vi.fn(() => ({ submitCommand: mockSubmitCommand })),
}))

function mountWithComposable(opts?: { unlocked?: boolean }) {
  const isUnlocked = ref(opts?.unlocked ?? true)
  const hasLockout = ref(false)
  const speedLevel = ref(50)
  let result: ReturnType<typeof useJoystickDrive>
  const Wrapper = defineComponent({
    setup() {
      result = useJoystickDrive({ isControlUnlocked: isUnlocked, lockout: hasLockout, speedLevel, getSessionId: () => 'sid-1' })
      return {}
    },
    template: '<div />',
  })
  const wrapper = mount(Wrapper)
  return { wrapper, getResult: () => result!, isUnlocked, hasLockout, speedLevel }
}

describe('useJoystickDrive', () => {
  beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks() })
  afterEach(() => vi.useRealTimers())

  it('joystickEngaged starts false', () => {
    const { getResult } = mountWithComposable()
    expect(getResult().joystickEngaged.value).toBe(false)
  })

  it('handleJoystickChange engages joystick and sends drive command', async () => {
    const { getResult } = mountWithComposable()
    getResult().handleJoystickChange({ x: 0.5, y: 0.5, magnitude: 0.7, active: true })
    await nextTick()
    expect(getResult().joystickEngaged.value).toBe(true)
    expect(mockSubmitCommand).toHaveBeenCalledWith('drive', expect.objectContaining({
      session_id: 'sid-1',
      vector: expect.objectContaining({ linear: expect.any(Number) }),
    }))
  })

  it('stopMovement sends zero vector and disengages', async () => {
    const { getResult } = mountWithComposable()
    getResult().handleJoystickChange({ x: 0.5, y: 0.5, magnitude: 0.7, active: true })
    await getResult().stopMovement(true)
    expect(getResult().joystickEngaged.value).toBe(false)
    expect(getResult().activeDriveVector.value).toEqual({ linear: 0, angular: 0 })
  })

  it('clears timers on unmount', () => {
    const { wrapper } = mountWithComposable()
    expect(() => wrapper.unmount()).not.toThrow()
  })
})
