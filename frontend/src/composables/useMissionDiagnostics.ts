import { ref, onMounted, onUnmounted } from 'vue'
import { useWebSocket } from '@/services/websocket'

export interface MissionDiagnosticsPayload {
  run_id: string
  mission_id: string
  blocked_command_count: number
  average_pose_quality: string | null
  heading_alignment_samples: number
  pose_update_count: number
}

export function useMissionDiagnostics() {
  const diagnostics = ref<MissionDiagnosticsPayload | null>(null)
  const socket = useWebSocket('telemetry')

  function onMessage(payload: unknown) {
    if (payload && typeof payload === 'object' && 'run_id' in payload) {
      diagnostics.value = payload as MissionDiagnosticsPayload
    }
  }

  onMounted(async () => {
    try {
      await socket.connect()
      socket.subscribe('mission.diagnostics', onMessage)
    } catch (error) {
      console.warn('useMissionDiagnostics: WS connect failed', error)
    }
  })

  onUnmounted(() => {
    socket.unsubscribe('mission.diagnostics', onMessage)
    socket.disconnect()
  })

  return { diagnostics }
}
