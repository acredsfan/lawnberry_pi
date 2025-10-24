import { defineStore } from 'pinia';
import { ref, toRaw } from 'vue';

const PREFERENCES_STORAGE_KEY = 'lawnberry_user_preferences';
const PREFERENCES_VERSION = 1;

// Define the shape of your preferences
export interface UserPreferences {
  version: number;
  theme: 'dark' | 'light';
  notifications: {
    mower_status: boolean;
    system_alerts: boolean;
  };
  [key: string]: any; // Allow for future flexibility
}

// Define default preferences for new users or for when a reset is needed
const defaultPreferences: UserPreferences = {
  version: PREFERENCES_VERSION,
  theme: 'dark',
  notifications: {
    mower_status: true,
    system_alerts: true,
  },
};

// Migration logic can be added here in the future.
// For now, we'll just handle the initial setup.
const migratePreferences = (loadedPrefs: any): UserPreferences => {
  if (!loadedPrefs || typeof loadedPrefs !== 'object') {
    return defaultPreferences;
  }

  // Example of a future migration:
  // if (loadedPrefs.version < 2) {
  //   // Apply changes for version 2
  //   loadedPrefs.newSetting = 'default_value';
  //   loadedPrefs.version = 2;
  // }

  // For now, just ensure the version is current
  loadedPrefs.version = PREFERENCES_VERSION;

  // Merge with defaults to add any new settings
  return { ...defaultPreferences, ...loadedPrefs };
};

export const useUserSettingsStore = defineStore('userSettings', () => {
  const preferences = ref<UserPreferences>(defaultPreferences);

  const loadPreferences = () => {
    try {
      const storedPrefs = localStorage.getItem(PREFERENCES_STORAGE_KEY);
      if (storedPrefs) {
        const parsedPrefs = JSON.parse(storedPrefs);
        preferences.value = migratePreferences(parsedPrefs);
      } else {
        // No stored settings, use defaults
        preferences.value = defaultPreferences;
      }
    } catch (error) {
      console.error('Failed to load user preferences:', error);
      // Fallback to defaults in case of error
      preferences.value = defaultPreferences;
    }
  };

  const savePreferences = () => {
    try {
      localStorage.setItem(PREFERENCES_STORAGE_KEY, JSON.stringify(toRaw(preferences.value)));
    } catch (error) {
      console.error('Failed to save user preferences:', error);
    }
  };

  const updatePreference = (key: string, value: any) => {
    // A simple key-value update. For nested objects, you might need a more complex updater.
    if (key in preferences.value) {
      (preferences.value as any)[key] = value;
      savePreferences();
    } else {
      console.warn(`Attempted to update non-existent preference: ${key}`);
    }
  };

  const setPreferences = (newPrefs: Partial<UserPreferences>) => {
    preferences.value = { ...preferences.value, ...newPrefs };
    savePreferences();
  };

  const resetPreferences = () => {
    preferences.value = defaultPreferences;
    savePreferences();
  };

  // Load preferences on store initialization
  loadPreferences();

  return {
    preferences,
    loadPreferences,
    updatePreference,
    setPreferences,
    resetPreferences,
  };
});
