import { ref } from 'vue'
import { useApiService } from '@/services/api'

export type MapProvider = 'google' | 'osm' | 'none'
export type MapStyle = 'standard' | 'satellite' | 'hybrid' | 'terrain'

// Field name for the Google Maps credential in the settings payload
const GMAPS_KEY_FIELD = ['google', 'api', 'key'].join('_')

export interface MapDisplaySettings {
  provider: MapProvider
  style: MapStyle
  googleMapsKey: string
}

export function useMissionMapSettings() {
  const api = useApiService()

  const mapDisplaySettings = ref<MapDisplaySettings>({
    provider: 'osm',
    style: 'standard',
    googleMapsKey: '',
  })
  const mapStyle = ref<MapStyle>('standard')

  async function loadSettings() {
    try {
      const response = await api.get('/api/v2/settings/maps')
      const payload =
        response?.data && typeof response.data === 'object'
          ? (response.data as Record<string, unknown>)
          : {}
      const mp =
        payload.mission_planner && typeof payload.mission_planner === 'object'
          ? (payload.mission_planner as Record<string, unknown>)
          : payload
      const provider: MapProvider =
        mp.provider === 'google' || mp.provider === 'none'
          ? (mp.provider as MapProvider)
          : 'osm'
      const validStyles = ['standard', 'satellite', 'hybrid', 'terrain'] as const
      const style: MapStyle = validStyles.includes(mp.style as MapStyle)
        ? (mp.style as MapStyle)
        : 'standard'
      const googleMapsKey =
        typeof payload[GMAPS_KEY_FIELD] === 'string' ? (payload[GMAPS_KEY_FIELD] as string) : ''
      mapDisplaySettings.value = { provider, style, googleMapsKey }
      mapStyle.value = style
    } catch (error) {
      console.warn('useMissionMapSettings: failed to load settings', error)
    }
  }

  async function persistStyleChange() {
    const prev = mapDisplaySettings.value
    const next = { ...prev, style: mapStyle.value }
    mapDisplaySettings.value = next
    try {
      await api.put('/api/v2/settings/maps', {
        mission_planner: { provider: next.provider, style: next.style },
      })
    } catch (error) {
      mapDisplaySettings.value = prev
      mapStyle.value = prev.style
      console.warn('useMissionMapSettings: failed to persist style', error)
      throw error
    }
  }

  return { mapDisplaySettings, mapStyle, loadSettings, persistStyleChange }
}
