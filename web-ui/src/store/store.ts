import { configureStore } from '@reduxjs/toolkit'
import mowerReducer from './slices/mowerSlice'
import weatherReducer from './slices/weatherSlice'
import settingsReducer from './slices/settingsSlice'
import navigationReducer from './slices/navigationSlice'
import uiReducer from './slices/uiSlice'

export const store = configureStore({
  reducer: {
    mower: mowerReducer,
    weather: weatherReducer,
    settings: settingsReducer,
    navigation: navigationReducer,
    ui: uiReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        ignoredActions: ['persist/PERSIST', 'persist/REHYDRATE'],
      },
    }),
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
