import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import MissionPlannerView from '@/views/MissionPlannerView.vue';
import { useMissionStore } from '@/stores/mission';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

// Mock Leaflet
vi.mock('leaflet', () => ({
  default: {
    map: vi.fn(() => ({
      setView: vi.fn(),
      on: vi.fn(),
      remove: vi.fn(),
      eachLayer: vi.fn(),
    })),
    tileLayer: vi.fn(() => ({
      addTo: vi.fn(),
    })),
    marker: vi.fn(() => ({
      addTo: vi.fn(),
    })),
  },
}));

describe('MissionPlannerView.vue', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it('renders the mission planner view', () => {
    const wrapper = mount(MissionPlannerView);
    expect(wrapper.find('h1').text()).toBe('Mission Planner');
  });

  it('allows creating a mission', async () => {
    const wrapper = mount(MissionPlannerView);
    const missionStore = useMissionStore();
    missionStore.addWaypoint(51.5, -0.09);
    
    await wrapper.find('input[placeholder="Mission Name"]').setValue('Test Mission');
    await wrapper.find('button').trigger('click'); // Create mission button
    
    expect(missionStore.createMission).toHaveBeenCalledWith('Test Mission');
  });
  
  // More tests for starting, pausing, etc.
});
