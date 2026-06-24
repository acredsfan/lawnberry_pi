export type MapProvider = 'google' | 'osm' | 'none'
export type MapStyle = 'standard' | 'satellite' | 'hybrid' | 'terrain'

export interface MapAlignmentData {
  north_m?: number
  east_m?: number
  method?: string
  control_point_count?: number
  rmse_m?: number | null
  created_at?: string | null
}

export interface MapAlignmentProfile {
  source_id: string
  provider: string
  layer: string
  dataset_revision?: string | null
  aliases?: string[]
  alignment?: MapAlignmentData
}

export interface MapDisplayTransformSettings {
  provider?: MapProvider
  style?: MapStyle
  active_source_id?: string | null
  mission_planner?: {
    provider?: MapProvider
    style?: MapStyle
    source_id?: string | null
  } | null
  alignment_profiles?: Record<string, MapAlignmentProfile>
  satellite_display_north_m?: number
  satellite_display_east_m?: number
}

export interface MapDisplayTransform {
  sourceId: string
  provider: string
  layer: string
  northM: number
  eastM: number
  method: string
  profileFound: boolean
  unaligned: boolean
}

const METERS_PER_LAT_DEG = 111320.0
export { METERS_PER_LAT_DEG }

export function resolveMapSourceId(
  provider: MapProvider = 'osm',
  style: MapStyle = 'standard',
  sourceId?: string | null,
): string {
  if (sourceId) return sourceId
  if (provider === 'google' && (style === 'satellite' || style === 'hybrid')) {
    return `google:${style}`
  }
  if (provider === 'osm' && style === 'satellite') return 'esri:world-imagery'
  if (provider === 'osm' && style === 'hybrid') return 'esri:world-imagery-hybrid'
  if (provider === 'none') return 'none'
  return `${provider}:${style}`
}

function isImagerySource(sourceId: string): boolean {
  return (
    sourceId.startsWith('google:satellite') ||
    sourceId.startsWith('google:hybrid') ||
    sourceId.startsWith('esri:world-imagery') ||
    sourceId.startsWith('custom:')
  )
}

function findProfile(
  profiles: Record<string, MapAlignmentProfile> | undefined,
  sourceId: string,
): MapAlignmentProfile | null {
  if (!profiles) return null
  if (profiles[sourceId]) return profiles[sourceId]
  return (
    Object.values(profiles).find(profile => Array.isArray(profile.aliases) && profile.aliases.includes(sourceId)) ??
    null
  )
}

export function createMapDisplayTransform(
  settings: MapDisplayTransformSettings | null | undefined,
  effectiveSourceId?: string | null,
): MapDisplayTransform {
  const mp = settings?.mission_planner ?? null
  const provider = (mp?.provider ?? settings?.provider ?? 'osm') as MapProvider
  const style = (mp?.style ?? settings?.style ?? 'standard') as MapStyle
  const sourceId = resolveMapSourceId(provider, style, effectiveSourceId ?? mp?.source_id ?? settings?.active_source_id)
  const profile = findProfile(settings?.alignment_profiles, sourceId)

  if (profile?.alignment) {
    return {
      sourceId,
      provider: profile.provider || provider,
      layer: profile.layer || style,
      northM: Number(profile.alignment.north_m ?? 0),
      eastM: Number(profile.alignment.east_m ?? 0),
      method: profile.alignment.method || 'profile',
      profileFound: true,
      unaligned: false,
    }
  }

  const legacyNorthM = Number(settings?.satellite_display_north_m ?? 0)
  const legacyEastM = Number(settings?.satellite_display_east_m ?? 0)
  if ((legacyNorthM !== 0 || legacyEastM !== 0) && isImagerySource(sourceId)) {
    return {
      sourceId,
      provider,
      layer: style,
      northM: legacyNorthM,
      eastM: legacyEastM,
      method: 'legacy_global_offset',
      profileFound: false,
      unaligned: false,
    }
  }

  return {
    sourceId,
    provider,
    layer: style,
    northM: 0,
    eastM: 0,
    method: 'none',
    profileFound: false,
    unaligned: isImagerySource(sourceId),
  }
}

export function applyDisplayTransform(lat: number, lon: number, transform: MapDisplayTransform): [number, number] {
  if (transform.northM === 0 && transform.eastM === 0) return [lat, lon]
  const metersPerLonDeg = METERS_PER_LAT_DEG * Math.cos((lat * Math.PI) / 180)
  return [lat + transform.northM / METERS_PER_LAT_DEG, lon + transform.eastM / metersPerLonDeg]
}

export function removeDisplayTransform(lat: number, lon: number, transform: MapDisplayTransform): [number, number] {
  if (transform.northM === 0 && transform.eastM === 0) return [lat, lon]
  const metersPerLonDeg = METERS_PER_LAT_DEG * Math.cos((lat * Math.PI) / 180)
  return [lat - transform.northM / METERS_PER_LAT_DEG, lon - transform.eastM / metersPerLonDeg]
}
