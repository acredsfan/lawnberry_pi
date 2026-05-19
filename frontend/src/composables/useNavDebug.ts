import { ref, onMounted, onUnmounted } from 'vue'
import { useWebSocket } from '@/services/websocket'
import type { MissionDiagnosticsPayload } from './useMissionDiagnostics'

export interface NavDebugPayload {
  mode: 'tank' | 'pre_rotate' | 'blend' | null
  heading_error_deg: number | null
  raw_heading_error_deg: number
  cross_track_error_m: number | null
  steer_deg: number | null
  stanley_k_cte: number
  stanley_dead_band_m: number
  distance_to_waypoint_m: number
  left_speed_cmd: number
  right_speed_cmd: number
  base_speed: number
  stall_boost: number
  traction_boost: number
  enc_rpm_a: number
  enc_rpm_b: number
  pre_rotating: boolean
  in_tank_mode: boolean
  gps_accuracy_m: number | null
}

export function useNavDebug() {
  const navDebug = ref<NavDebugPayload | null>(null)
  const diagnostics = ref<MissionDiagnosticsPayload | null>(null)
  const socket = useWebSocket('telemetry')

  function onNavDebug(payload: unknown) {
    if (payload && typeof payload === 'object' && 'mode' in payload) {
      navDebug.value = payload as NavDebugPayload
    }
  }

  function onDiagnostics(payload: unknown) {
    if (payload && typeof payload === 'object' && 'run_id' in payload) {
      diagnostics.value = payload as MissionDiagnosticsPayload
    }
  }

  onMounted(async () => {
    try {
      await socket.connect()
      socket.subscribe('telemetry.nav_debug', onNavDebug)
      socket.subscribe('mission.diagnostics', onDiagnostics)
    } catch (error) {
      console.warn('useNavDebug: WS connect failed', error)
    }
  })

  onUnmounted(() => {
    socket.unsubscribe('telemetry.nav_debug', onNavDebug)
    socket.unsubscribe('mission.diagnostics', onDiagnostics)
  })

  return { navDebug, diagnostics }
}
