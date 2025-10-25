import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import MissionPlannerView from '@/views/MissionPlannerView.vue';
import { useMissionStore } from '@/stores/mission';
import { useMapStore } from '@/stores/map';
import apiService from '@/services/api';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mapPaneStub = { _leaflet_pos: { x: 0, y: 0 } }

const layerGroupInstance = {
  addTo: vi.fn(() => layerGroupInstance),
  clearLayers: vi.fn(),
  removeLayer: vi.fn(),
}

const tileLayerInstance = {
  addTo: vi.fn(() => tileLayerInstance),
}

const markerInstance = {
  addTo: vi.fn(() => markerInstance),
  on: vi.fn(),
  setLatLng: vi.fn(),
}

const polylineInstance = {
  addTo: vi.fn(() => polylineInstance),
}

const circleInstance = {
  addTo: vi.fn(() => circleInstance),
}

const circleMarkerInstance = {
  addTo: vi.fn(() => circleMarkerInstance),
}

const mapInstance = {
  setView: vi.fn(),
  on: vi.fn((event: string, handler: () => void) => {
    if (event === 'load') {
      handler()
    }
  }),
  off: vi.fn(),
  remove: vi.fn(),
  eachLayer: vi.fn(),
  whenReady: vi.fn((handler: () => void) => handler()),
  getZoom: vi.fn(() => 18),
  _mapPane: mapPaneStub,
}

// Mock Leaflet with required stubs
vi.mock('leaflet', () => ({
  default: {
    map: vi.fn(() => mapInstance),
    layerGroup: vi.fn(() => layerGroupInstance),
    tileLayer: vi.fn(() => tileLayerInstance),
    marker: vi.fn(() => markerInstance),
    polyline: vi.fn(() => polylineInstance),
    circle: vi.fn(() => circleInstance),
    circleMarker: vi.fn(() => circleMarkerInstance),
    divIcon: vi.fn(() => ({})),
    Icon: {
      Default: {
        mergeOptions: vi.fn(),
      },
    },
  },
}));

vi.mock('@/components/MissionWaypointList.vue', () => ({
  default: {
    name: 'MissionWaypointList',
    template: '<div class="mission-waypoint-list" />',
  },
}))

const mockedApi = apiService as unknown as {
  get: ReturnType<typeof vi.fn>
  post: ReturnType<typeof vi.fn>
}

function primeMapStore() {
  const mapStore = useMapStore()
  mapStore.configuration = {
    config_id: 'default',
    config_version: 1,
    provider: 'osm',
    provider_metadata: {},
    boundary_zone: null,
    exclusion_zones: [],
    mowing_zones: [],
    markers: [],
    center_point: null,
    zoom_level: 18,
    map_rotation_deg: 0,
    validation_errors: [],
    last_modified: '2025-10-25T15:28:33.451Z',
    created_at: '2025-10-25T15:28:33.451Z',
  } as any
  mapStore.loadConfiguration = vi.fn().mockResolvedValue(undefined)
}

describe('MissionPlannerView.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    primeMapStore()

    mockedApi.get.mockImplementation((url: string) => {
      if (url.startsWith('/api/v2/settings/maps')) {
        return Promise.resolve({ data: { provider: 'osm', style: 'standard', google_api_key: '' } })
      }
      if (url.startsWith('/api/v2/map/configuration')) {
        return Promise.resolve({ data: { provider: 'osm', zones: [], markers: [], updated_at: '2025-10-25T15:28:33.451Z' } })
      }
      return Promise.resolve({ data: {} })
    })

    mockedApi.post.mockResolvedValue({ data: {} })
  })

  it('renders the mission planner view', async () => {
    const wrapper = mount(MissionPlannerView)
    await flushPromises()
    expect(wrapper.find('h1').text()).toBe('Mission Planner')
  })

  it('allows creating a mission', async () => {
    const wrapper = mount(MissionPlannerView)
    const missionStore = useMissionStore()
    missionStore.addWaypoint(51.5, -0.09)
    const createMissionSpy = vi.spyOn(missionStore, 'createMission').mockResolvedValue(undefined as any)

    await flushPromises()
    const nameInput = wrapper.find('input[placeholder="Mission Name"]')
    await nameInput.setValue('Test Mission')
    const createButton = wrapper.findAll('button').find(btn => btn.text() === 'Create Mission')!
    await createButton.trigger('click')

    expect(createMissionSpy).toHaveBeenCalledWith('Test Mission')
  })
})
