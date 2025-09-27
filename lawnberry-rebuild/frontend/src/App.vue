<template>
  <div id="app">
    <header class="app-header">
      <nav class="navbar">
        <div class="nav-brand">
          <img src="/lawnberry-icon.svg" alt="LawnBerry Pi" class="logo">
          <h1>LawnBerry Pi v2</h1>
        </div>
        <div class="nav-links">
          <router-link to="/" class="nav-link">Dashboard</router-link>
          <router-link to="/control" class="nav-link">Control</router-link>
          <router-link to="/maps" class="nav-link">Maps</router-link>
          <router-link to="/planning" class="nav-link">Planning</router-link>
          <router-link to="/settings" class="nav-link">Settings</router-link>
        </div>
        <div class="nav-user">
          <UserMenu v-if="user" />
          <router-link v-else to="/login" class="login-link">
            Sign In
          </router-link>
        </div>
      </nav>
    </header>
    
    <main class="app-main">
      <router-view />
    </main>
    
    <footer class="app-footer">
      <div class="status-bar">
        <div class="system-status" :class="systemStatus">
          <span class="status-indicator" />
          System: {{ systemStatus }}
        </div>
        <div class="connection-status" :class="connectionStatus">
          <span class="status-indicator" />
          Connection: {{ connectionStatus }}
        </div>
      </div>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useAuthStore } from './stores/auth'
import { useSystemStore } from './stores/system'
import UserMenu from './components/UserMenu.vue'

const authStore = useAuthStore()
const systemStore = useSystemStore()

const user = computed(() => authStore.user)
const systemStatus = computed(() => systemStore.status)
const connectionStatus = computed(() => systemStore.connectionStatus)

onMounted(async () => {
  // Initialize system store
  systemStore.initialize()
  
  // Validate user session on app start
  if (authStore.token) {
    await authStore.validateSession()
  }
  
  // Track user activity for session management
  const activityEvents = ['mousedown', 'mousemove', 'keypress', 'scroll', 'touchstart']
  
  const handleActivity = () => {
    authStore.updateActivity()
  }
  
  activityEvents.forEach(event => {
    document.addEventListener(event, handleActivity, { passive: true })
  })
})
</script>

<style scoped>
.app-header {
  background: #2c3e50;
  color: white;
  padding: 0;
  box-shadow: 0 2px 4px rgba(0,0,0,0.1);
}

.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 2rem;
  max-width: 1400px;
  margin: 0 auto;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.logo {
  height: 40px;
  width: auto;
}

.nav-brand h1 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 600;
}

.nav-links {
  display: flex;
  gap: 2rem;
}

.nav-link {
  color: white;
  text-decoration: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  transition: background-color 0.2s;
}

.nav-link:hover,
.nav-link.router-link-active {
  background-color: rgba(255,255,255,0.1);
}

.nav-user {
  position: relative;
}

.login-link {
  color: white;
  text-decoration: none;
  padding: 0.5rem 1rem;
  border: 1px solid rgba(255,255,255,0.3);
  border-radius: 4px;
  transition: background-color 0.2s;
}

.login-link:hover {
  background-color: rgba(255,255,255,0.1);
  text-decoration: none;
}

.app-main {
  flex: 1;
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
}

.app-footer {
  background: #34495e;
  color: white;
  padding: 0;
}

.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 2rem;
  max-width: 1400px;
  margin: 0 auto;
  font-size: 0.875rem;
}

.system-status,
.connection-status {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.status-indicator {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #95a5a6;
}

.online .status-indicator,
.active .status-indicator {
  background: #27ae60;
}

.offline .status-indicator,
.error .status-indicator {
  background: #e74c3c;
}

.warning .status-indicator {
  background: #f39c12;
}

@media (max-width: 768px) {
  .navbar {
    flex-direction: column;
    gap: 1rem;
    padding: 1rem;
  }
  
  .nav-links {
    gap: 1rem;
  }
  
  .app-main {
    padding: 1rem;
  }
  
  .status-bar {
    flex-direction: column;
    gap: 0.5rem;
    text-align: center;
  }
}
</style>