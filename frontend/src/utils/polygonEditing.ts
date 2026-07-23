export interface PolygonVertex {
  latitude: number
  longitude: number
}

export function removePolygonVertex<T extends PolygonVertex>(
  points: readonly T[],
  index: number,
): T[] {
  if (!Number.isInteger(index) || index < 0 || index >= points.length) {
    throw new Error('Boundary point does not exist')
  }
  if (points.length <= 3) {
    throw new Error('A boundary needs at least three points')
  }
  return points.filter((_, pointIndex) => pointIndex !== index)
}
