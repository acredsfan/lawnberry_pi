import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { useBoundaryGeometry } from '@/composables/useBoundaryGeometry'

function mountWithComposable() {
  let result: ReturnType<typeof useBoundaryGeometry>
  const Wrapper = defineComponent({
    setup() { result = useBoundaryGeometry(); return {} },
    template: '<div />',
  })
  mount(Wrapper)
  return () => result!
}

describe('useBoundaryGeometry', () => {
  it('starts with empty vertices and zero area', () => {
    const getResult = mountWithComposable()
    expect(getResult().vertices.value).toHaveLength(0)
    expect(getResult().areaM2.value).toBe(0)
  })

  it('addVertex appends to vertices', () => {
    const getResult = mountWithComposable()
    getResult().addVertex(37.0, -122.0)
    getResult().addVertex(37.001, -122.0)
    getResult().addVertex(37.001, -122.001)
    expect(getResult().vertices.value).toHaveLength(3)
  })

  it('areaM2 is non-zero for a triangle', () => {
    const getResult = mountWithComposable()
    getResult().addVertex(37.0, -122.0)
    getResult().addVertex(37.001, -122.0)
    getResult().addVertex(37.001, -122.001)
    expect(getResult().areaM2.value).toBeGreaterThan(0)
  })

  it('removeVertex removes the correct vertex', () => {
    const getResult = mountWithComposable()
    getResult().addVertex(37.0, -122.0)
    getResult().addVertex(37.001, -122.0)
    getResult().removeVertex(0)
    expect(getResult().vertices.value).toHaveLength(1)
    expect(getResult().vertices.value[0].lat).toBeCloseTo(37.001)
  })

  it('clearVertices empties the list', () => {
    const getResult = mountWithComposable()
    getResult().addVertex(37.0, -122.0)
    getResult().clearVertices()
    expect(getResult().vertices.value).toHaveLength(0)
    expect(getResult().areaM2.value).toBe(0)
  })
})
