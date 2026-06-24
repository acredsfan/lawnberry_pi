export interface LocationLike {
  protocol: string
  hostname: string
}

export type TileLayerOverlay = {
  url: string
  attribution?: string
  subdomains?: string | string[]
  maxZoom?: number
  maxNativeZoom?: number
}

export type TileLayerConfig = {
  url: string
  attribution: string
  subdomains?: string | string[]
  maxZoom?: number
  maxNativeZoom?: number
  overlay?: TileLayerOverlay
}

export type CustomImagerySource = {
  id: string
  name: string
  type: 'xyz' | 'arcgis'
  url_template: string
  attribution?: string | null
  min_zoom?: number | null
  max_zoom?: number | null
  max_native_zoom?: number | null
  dataset_revision?: string | null
  enabled?: boolean
}

const PRIVATE_IPV4_REGEX = /^(10\.|192\.168\.|172\.(1[6-9]|2[0-9]|3[0-1])\.)/
const LOCAL_SUFFIXES = ['.local', '.lan', '.home', '.internal']

const OSM_TILE_LAYERS: Record<string, TileLayerConfig> = {
  standard: {
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    attribution: '© OpenStreetMap contributors',
    subdomains: ['a', 'b', 'c'],
    maxZoom: 19,
  },
  satellite: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
    maxZoom: 22,
    maxNativeZoom: 19,
  },
  hybrid: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Imagery © Esri',
    maxZoom: 22,
    maxNativeZoom: 19,
    overlay: {
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      attribution: 'Labels © Esri',
      maxZoom: 22,
      maxNativeZoom: 19,
    },
  },
  terrain: {
    url: 'https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png',
    attribution: 'Map data © OpenStreetMap contributors, SRTM | Map style © OpenTopoMap (CC-BY-SA)',
    subdomains: ['a', 'b', 'c'],
    maxZoom: 17,
  },
}

export function isSecureMapsContext(location: LocationLike | null | undefined): boolean {
  if (!location) return false
  const protocol = (location.protocol || '').toLowerCase()
  if (protocol === 'https:') return true

  const host = (location.hostname || '').toLowerCase()
  if (!host) return false
  if (host === 'localhost' || host === '127.0.0.1' || host === '::1') return true
  if (PRIVATE_IPV4_REGEX.test(host)) return true
  if (LOCAL_SUFFIXES.some(suffix => host.endsWith(suffix))) return true
  if (!host.includes('.')) return true
  return false
}

export function shouldUseGoogleProvider(
  provider: string | null | undefined,
  apiKey: string | null | undefined,
  location: LocationLike | null | undefined
): boolean {
  if (provider !== 'google') return false
  if (!apiKey || !apiKey.trim()) return false
  return isSecureMapsContext(location)
}

export function getOsmTileLayer(style: string | null | undefined): TileLayerConfig {
  const key = (style || 'standard').toLowerCase().trim()
  return OSM_TILE_LAYERS[key] || OSM_TILE_LAYERS.standard
}

export function resolveCustomSourceId(source: CustomImagerySource): string {
  return `custom:${source.id}`
}

export function findCustomImagerySource(
  sources: CustomImagerySource[] | null | undefined,
  sourceId: string | null | undefined,
): CustomImagerySource | null {
  if (!sourceId || !sourceId.startsWith('custom:')) return null
  const id = sourceId.slice('custom:'.length)
  return (sources ?? []).find(source => source.enabled !== false && source.id === id) ?? null
}

export function getCustomTileLayer(source: CustomImagerySource): TileLayerConfig {
  return {
    url: source.url_template,
    attribution: source.attribution || source.name,
    maxZoom: source.max_zoom ?? 22,
    maxNativeZoom: source.max_native_zoom ?? source.max_zoom ?? undefined,
  }
}
