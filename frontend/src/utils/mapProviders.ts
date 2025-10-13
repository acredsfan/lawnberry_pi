export interface LocationLike {
  protocol: string
  hostname: string
}

export type TileLayerOverlay = {
  url: string
  attribution?: string
  subdomains?: string | string[]
  maxZoom?: number
}

export type TileLayerConfig = {
  url: string
  attribution: string
  subdomains?: string | string[]
  maxZoom?: number
  overlay?: TileLayerOverlay
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
    maxZoom: 19,
  },
  hybrid: {
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Imagery © Esri',
    maxZoom: 19,
    overlay: {
      url: 'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
      attribution: 'Labels © Esri',
      maxZoom: 19,
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
