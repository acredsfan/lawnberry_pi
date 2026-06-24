import { ref } from 'vue'
import { useApiService } from '@/services/api'
import type { MapAlignmentProfile } from '@/utils/mapDisplayTransform'
import type { CustomImagerySource } from '@/utils/mapProviders'

export type MapProvider = 'google' | 'osm' | 'none'
export type MapStyle = 'standard' | 'satellite' | 'hybrid' | 'terrain'

// Field name for the Google Maps credential in the settings payload
const GMAPS_KEY_FIELD = ['google', 'api', 'key'].join('_')

export interface MapDisplaySettings {
  provider: MapProvider
  style: MapStyle
  googleMapsKey: string
  satelliteDisplayNorthM: number
  satelliteDisplayEastM: number
  activeSourceId: string | null
  alignmentProfiles: Record<string, MapAlignmentProfile>
  customSources: CustomImagerySource[]
  mission_planner?: {
    provider: MapProvider
    style: MapStyle
    source_id?: string | null
  }
}

export function useMissionMapSettings() {
  const api = useApiService()

  const mapDisplaySettings = ref<MapDisplaySettings>({
    provider: 'osm',
    style: 'standard',
    googleMapsKey: '',
    satelliteDisplayNorthM: 0,
    satelliteDisplayEastM: 0,
    activeSourceId: null,
    alignmentProfiles: {},
    customSources: [],
  })
  const mapStyle = ref<MapStyle>('standard')

  async function loadSettings() {
    try {
      const response = await api.get('/api/v2/settings/maps', { headers: { 'Cache-Control': 'no-cache' } })
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
      const satelliteDisplayNorthM =
        typeof payload.satellite_display_north_m === 'number' ? payload.satellite_display_north_m : 0
      const satelliteDisplayEastM =
        typeof payload.satellite_display_east_m === 'number' ? payload.satellite_display_east_m : 0
      const activeSourceId = typeof payload.active_source_id === 'string' ? payload.active_source_id : null
      const alignmentProfiles =
        payload.alignment_profiles && typeof payload.alignment_profiles === 'object'
          ? (payload.alignment_profiles as Record<string, MapAlignmentProfile>)
          : {}
      const customSources = Array.isArray(payload.custom_sources)
        ? (payload.custom_sources as CustomImagerySource[])
        : []
      const sourceId = typeof mp.source_id === 'string' ? mp.source_id : activeSourceId
      mapDisplaySettings.value = {
        provider,
        style,
        googleMapsKey,
        satelliteDisplayNorthM,
        satelliteDisplayEastM,
        activeSourceId,
        alignmentProfiles,
        customSources,
        mission_planner: { provider, style, source_id: sourceId },
      }
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
