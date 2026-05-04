import { ref, computed } from 'vue'

export interface LatLng { lat: number; lon: number }

/**
 * Manages boundary polygon vertices and computes geodetic area using the
 * shoelace formula over equirectangular-projected coordinates.
 */
export function useBoundaryGeometry() {
  const vertices = ref<LatLng[]>([])

  const areaM2 = computed(() => {
    const pts = vertices.value
    if (pts.length < 3) return 0
    const R = 6371000 // Earth radius in metres
    let area = 0
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const xi = (pts[i].lon * Math.PI / 180) * R * Math.cos(pts[i].lat * Math.PI / 180)
      const yi = (pts[i].lat * Math.PI / 180) * R
      const xj = (pts[j].lon * Math.PI / 180) * R * Math.cos(pts[j].lat * Math.PI / 180)
      const yj = (pts[j].lat * Math.PI / 180) * R
      area += xi * yj - xj * yi
    }
    return Math.abs(area / 2)
  })

  function addVertex(lat: number, lon: number): void {
    vertices.value.push({ lat, lon })
  }

  function removeVertex(index: number): void {
    vertices.value.splice(index, 1)
  }

  function clearVertices(): void {
    vertices.value = []
  }

  return { vertices, areaM2, addVertex, removeVertex, clearVertices }
}
