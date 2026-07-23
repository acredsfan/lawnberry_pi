import { describe, expect, it } from 'vitest'

import { removePolygonVertex } from '@/utils/polygonEditing'

const square = [
  { latitude: 40.0, longitude: -75.0 },
  { latitude: 40.0, longitude: -74.9 },
  { latitude: 39.9, longitude: -74.9 },
  { latitude: 39.9, longitude: -75.0 },
]

describe('removePolygonVertex', () => {
  it('V93 removes only the selected saved-boundary point', () => {
    const result = removePolygonVertex(square, 1)

    expect(result).toEqual([square[0], square[2], square[3]])
    expect(square).toHaveLength(4)
  })

  it('V93 refuses to reduce a boundary below three points', () => {
    expect(() => removePolygonVertex(square.slice(0, 3), 1)).toThrow(
      'A boundary needs at least three points',
    )
  })
})
