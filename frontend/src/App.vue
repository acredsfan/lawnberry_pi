<template>
  <div id="app" class="retro-app">
    <div class="retro-grid-bg" />
    <header class="app-header">
      <nav class="navbar">
        <div class="nav-brand">
          <img src="/LawnBerryPi_logo.png" alt="LawnBerry Pi" class="logo">
          <h1 class="retro-title">LawnBerry Pi v2</h1>
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
/* 1980s Techno Theme */
.retro-app {
  background: #0a0a0a;
  color: #00ffff;
  min-height: 100vh;
  font-family: 'Courier New', 'Consolas', monospace;
  position: relative;
  overflow-x: hidden;
}

.retro-grid-bg {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background-image: 
    linear-gradient(rgba(0, 255, 255, 0.08) 1px, transparent 1px),
    linear-gradient(90deg, rgba(0, 255, 255, 0.08) 1px, transparent 1px),
    radial-gradient(circle at 25% 25%, rgba(255, 0, 255, 0.05) 0%, transparent 50%),
    radial-gradient(circle at 75% 75%, rgba(0, 255, 255, 0.05) 0%, transparent 50%);
  background-size: 40px 40px, 40px 40px, 200px 200px, 300px 300px;
  z-index: -1;
  animation: gridPulse 6s ease-in-out infinite, gridShift 20s linear infinite;
}

@keyframes gridShift {
  0% { background-position: 0 0, 0 0, 0 0, 0 0; }
  100% { background-position: 40px 40px, 40px 40px, 200px 200px, 300px 300px; }
}

@keyframes gridPulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 0.6; }
}

.app-header {
  background: linear-gradient(135deg, #1a1a1a 0%, #2d1b69 50%, #0d0d0d 100%);
  color: #00ffff;
  padding: 0;
  box-shadow: 0 4px 20px rgba(0, 255, 255, 0.3);
  border-bottom: 2px solid #00ffff;
  position: relative;
}

.app-header::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, transparent, #00ffff, #ff00ff, #00ffff, transparent);
  animation: neonSweep 3s linear infinite;
}

@keyframes neonSweep {
  0% { transform: translateX(-100%); }
  100% { transform: translateX(100%); }
}

.navbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 2rem;
  max-width: 1400px;
  margin: 0 auto;
  position: relative;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.logo {
  height: 50px;
  width: auto;
  filter: drop-shadow(0 0 10px #00ffff);
  animation: logoGlow 2s ease-in-out infinite alternate;
}

@keyframes logoGlow {
  from { filter: drop-shadow(0 0 10px #00ffff); }
  to { filter: drop-shadow(0 0 20px #00ffff) drop-shadow(0 0 30px #ff00ff); }
}

.retro-title {
  margin: 0;
  font-size: 1.8rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 3px;
  background: linear-gradient(45deg, #00ffff, #ff00ff, #00ffff);
  background-size: 200% 200%;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  animation: textGlow 3s ease-in-out infinite;
}

@keyframes textGlow {
  0%, 100% { background-position: 0% 50%; }
  50% { background-position: 100% 50%; }
}

.nav-links {
  display: flex;
  gap: 0.5rem;
}

.nav-link {
  color: #00ffff;
  text-decoration: none;
  padding: 0.8rem 1.5rem;
  border: 1px solid transparent;
  border-radius: 0;
  transition: all 0.3s ease;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 1px;
  position: relative;
  background: rgba(0, 255, 255, 0.05);
  clip-path: polygon(10px 0, 100% 0, calc(100% - 10px) 100%, 0 100%);
}

.nav-link::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: linear-gradient(45deg, transparent, rgba(0, 255, 255, 0.1), transparent);
  opacity: 0;
  transition: opacity 0.3s ease;
}

.nav-link:hover::before,
.nav-link.router-link-active::before {
  opacity: 1;
}

.nav-link:hover,
.nav-link.router-link-active {
  color: #ffffff;
  border-color: #00ffff;
  box-shadow: 0 0 15px rgba(0, 255, 255, 0.5);
  text-shadow: 0 0 10px #00ffff;
}

.nav-user {
  position: relative;
}

.login-link {
  color: #00ffff;
  text-decoration: none;
  padding: 0.8rem 1.5rem;
  border: 2px solid #00ffff;
  background: rgba(0, 255, 255, 0.1);
  transition: all 0.3s ease;
  text-transform: uppercase;
  font-weight: 600;
  letter-spacing: 1px;
  clip-path: polygon(10px 0, 100% 0, calc(100% - 10px) 100%, 0 100%);
}

.login-link:hover {
  background: rgba(0, 255, 255, 0.2);
  box-shadow: 0 0 20px rgba(0, 255, 255, 0.6);
  text-shadow: 0 0 5px #00ffff;
  text-decoration: none;
}

.app-main {
  flex: 1;
  padding: 2rem;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  box-sizing: border-box;
  position: relative;
  z-index: 1;
}

.app-footer {
  background: linear-gradient(135deg, #1a1a1a 0%, #2d1b69 50%, #0d0d0d 100%);
  color: #00ffff;
  padding: 0;
  border-top: 2px solid #00ffff;
  box-shadow: 0 -4px 20px rgba(0, 255, 255, 0.2);
}

.status-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  max-width: 1400px;
  margin: 0 auto;
  font-size: 0.9rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.system-status,
.connection-status {
  display: flex;
  align-items: center;
  gap: 0.8rem;
  padding: 0.5rem 1rem;
  background: rgba(0, 255, 255, 0.05);
  border: 1px solid rgba(0, 255, 255, 0.3);
  clip-path: polygon(5px 0, 100% 0, calc(100% - 5px) 100%, 0 100%);
}

.status-indicator {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #666;
  box-shadow: 0 0 10px currentColor;
  animation: statusPulse 2s ease-in-out infinite;
}

@keyframes statusPulse {
  0%, 100% { transform: scale(1); opacity: 0.8; }
  50% { transform: scale(1.2); opacity: 1; }
}

.online .status-indicator,
.active .status-indicator {
  background: #00ff00;
  color: #00ff00;
}

.offline .status-indicator,
.error .status-indicator {
  background: #ff0040;
  color: #ff0040;
}

.warning .status-indicator {
  background: #ffff00;
  color: #ffff00;
}

@media (max-width: 768px) {
  .navbar {
    flex-direction: column;
    gap: 1rem;
    padding: 1rem;
  }
  
  .nav-links {
    gap: 0.5rem;
    flex-wrap: wrap;
    justify-content: center;
  }
  
  .nav-link {
    padding: 0.6rem 1rem;
    font-size: 0.9rem;
  }
  
  .app-main {
    padding: 1rem;
  }
  
  .status-bar {
    flex-direction: column;
    gap: 1rem;
    text-align: center;
  }
  
  .retro-title {
    font-size: 1.4rem;
    letter-spacing: 2px;
  }
}

/* Global retro scrollbar */
:global(::-webkit-scrollbar) {
  width: 8px;
}

:global(::-webkit-scrollbar-track) {
  background: #1a1a1a;
}

:global(::-webkit-scrollbar-thumb) {
  background: #00ffff;
  border-radius: 4px;
}

:global(::-webkit-scrollbar-thumb:hover) {
  background: #ff00ff;
}
</style>