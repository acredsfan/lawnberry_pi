import { ref, computed } from 'vue'

// Convert lat/lon to OSM tile X/Y at zoom z
function latLonToTile(lat: number, lon: number, z: number): { x: number; y: number } {
  const latRad = (lat * Math.PI) / 180
  const n = Math.pow(2, z)
  const x = Math.floor(((lon + 180) / 360) * n)
  const y = Math.floor(
    (1 - Math.log(Math.tan(latRad) + 1 / Math.cos(latRad)) / Math.PI) / 2 * n
  )
  return { x, y }
}

export function useOfflineMaps() {
  const offline = ref(localStorage.getItem('OFFLINE_MAPS') === '1')

  const isOffline = computed(() => offline.value)

  function setOffline(enabled: boolean) {
    offline.value = enabled
    localStorage.setItem('OFFLINE_MAPS', enabled ? '1' : '0')
  }

  function tileUrl(z: number, x: number, y: number): string {
    // OSM standard tile server; no API key required
    return `https://a.tile.openstreetmap.org/${z}/${x}/${y}.png`
  }

  function tileUrlFor(lat: number, lon: number, z: number): string {
    const { x, y } = latLonToTile(lat, lon, z)
    return tileUrl(z, x, y)
  }

  const providerName = computed(() => (offline.value ? 'OSM (offline fallback)' : 'OSM'))
  const attribution = computed(
    () => 'Map data © OpenStreetMap contributors'
  )

  return {
    isOffline,
    setOffline,
    providerName,
    attribution,
    tileUrl,
    tileUrlFor,
  }
}
