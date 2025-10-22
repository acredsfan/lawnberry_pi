import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router/index'
import './assets/main.css'
import './assets/theme.css'
import { useAuthStore } from './stores/auth'
import { useMapStore } from './stores/map'
import { useControlStore } from './stores/control'
import { usePreferencesStore } from './stores/preferences'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)
app.use(router)

if (typeof window !== 'undefined') {
	const search = window.location?.search ?? ''
	const enableE2EHarness = search.includes('e2e=1') || search.includes('e2e=true')

	if (enableE2EHarness) {
		const hooks = {
			pinia,
			get authStore() {
				return useAuthStore()
			},
			get mapStore() {
				return useMapStore()
			},
			get controlStore() {
				return useControlStore()
			},
			get preferencesStore() {
				return usePreferencesStore()
			},
			reset() {
				useAuthStore().$reset()
				useMapStore().$reset()
				useControlStore().$reset()
				usePreferencesStore().$reset?.()
				window.localStorage.clear()
				window.sessionStorage?.clear?.()
			},
		}

		Object.defineProperty(window, '__APP_TEST_HOOKS__', {
			value: hooks,
			configurable: false,
			enumerable: false,
			writable: false,
		})
	}
}

app.mount('#app')