<template>
  <div class="user-menu" :class="{ 'menu-open': showMenu }">
    <button 
      @click="toggleMenu" 
      class="user-button"
      :aria-expanded="showMenu"
      aria-haspopup="true"
    >
      <span class="user-avatar">
        {{ user?.username?.charAt(0).toUpperCase() || 'U' }}
      </span>
      <span class="user-info">
        <span class="user-name">{{ user?.username || 'Guest' }}</span>
        <span class="user-role">{{ user?.role || 'user' }}</span>
      </span>
      <span class="menu-arrow" :class="{ rotated: showMenu }">▼</span>
    </button>
    
    <div v-if="showMenu" class="user-dropdown" @click.stop>
      <div class="dropdown-header">
        <div class="user-details">
          <strong>{{ user?.username }}</strong>
          <small>{{ user?.email || 'No email' }}</small>
        </div>
        <div class="session-info">
          <small v-if="timeUntilExpiry">
            Session expires in {{ formatTimeRemaining(timeUntilExpiry) }}
          </small>
          <small v-if="isTokenExpiringSoon" class="text-warning">
            ⚠️ Session expiring soon
          </small>
        </div>
      </div>
      
      <div class="dropdown-divider"></div>
      
      <div class="dropdown-actions">
        <button @click="handleRefreshToken" class="dropdown-item" :disabled="isLoading">
          <span class="item-icon">🔄</span>
          {{ isLoading ? 'Refreshing...' : 'Refresh Session' }}
        </button>
        
        <button @click="handleLogout" class="dropdown-item logout-item">
          <span class="item-icon">🚪</span>
          Sign Out
        </button>
      </div>
    </div>
    
    <!-- Overlay to close menu -->
    <div v-if="showMenu" class="menu-overlay" @click="closeMenu"></div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const showMenu = ref(false)
const isLoading = ref(false)

const user = computed(() => authStore.user)
const timeUntilExpiry = computed(() => authStore.timeUntilExpiry)
const isTokenExpiringSoon = computed(() => authStore.isTokenExpiringSoon)

const toggleMenu = () => {
  showMenu.value = !showMenu.value
}

const closeMenu = () => {
  showMenu.value = false
}

const formatTimeRemaining = (ms: number) => {
  const minutes = Math.floor(ms / (1000 * 60))
  const hours = Math.floor(minutes / 60)
  
  if (hours > 0) {
    return `${hours}h ${minutes % 60}m`
  }
  return `${minutes}m`
}

const handleRefreshToken = async () => {
  try {
    isLoading.value = true
    await authStore.refreshToken()
    closeMenu()
  } catch (error) {
    console.error('Failed to refresh token:', error)
  } finally {
    isLoading.value = false
  }
}

const handleLogout = async () => {
  try {
    await authStore.logout()
    router.push('/login')
  } catch (error) {
    console.error('Logout failed:', error)
    // Force redirect anyway
    router.push('/login')
  }
}

// Close menu when clicking outside
const handleClickOutside = (event: MouseEvent) => {
  const target = event.target as Element
  if (showMenu.value && !target.closest('.user-menu')) {
    closeMenu()
  }
}

onMounted(() => {
  document.addEventListener('click', handleClickOutside)
})

onUnmounted(() => {
  document.removeEventListener('click', handleClickOutside)
})
</script>

<style scoped>
.user-menu {
  position: relative;
}

.user-button {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  background: transparent;
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.2s ease;
  min-width: 0;
}

.user-button:hover {
  background-color: rgba(255, 255, 255, 0.1);
  border-color: rgba(255, 255, 255, 0.3);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #3498db;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 0.875rem;
  flex-shrink: 0;
}

.user-info {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  min-width: 0;
  flex: 1;
}

.user-name {
  font-weight: 500;
  font-size: 0.875rem;
  line-height: 1.2;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  width: 100%;
}

.user-role {
  font-size: 0.75rem;
  opacity: 0.8;
  text-transform: capitalize;
  line-height: 1;
}

.menu-arrow {
  font-size: 0.75rem;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}

.menu-arrow.rotated {
  transform: rotate(180deg);
}

.user-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 0.5rem;
  background: white;
  border: 1px solid #e9ecef;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  min-width: 280px;
  z-index: 1000;
  color: #2c3e50;
}

.dropdown-header {
  padding: 1rem;
}

.user-details strong {
  display: block;
  font-size: 1rem;
  margin-bottom: 0.25rem;
}

.user-details small {
  color: #6c757d;
  font-size: 0.875rem;
}

.session-info {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px solid #f1f3f4;
}

.session-info small {
  display: block;
  font-size: 0.75rem;
  color: #6c757d;
}

.session-info .text-warning {
  color: #f39c12 !important;
  font-weight: 500;
}

.dropdown-divider {
  height: 1px;
  background: #e9ecef;
  margin: 0;
}

.dropdown-actions {
  padding: 0.5rem 0;
}

.dropdown-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  width: 100%;
  padding: 0.75rem 1rem;
  border: none;
  background: none;
  color: #2c3e50;
  font-size: 0.875rem;
  text-align: left;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.dropdown-item:hover {
  background-color: #f8f9fa;
}

.dropdown-item:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.logout-item {
  color: #e74c3c;
}

.logout-item:hover {
  background-color: #fee;
}

.item-icon {
  font-size: 1rem;
  flex-shrink: 0;
}

.menu-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 999;
  background: transparent;
}

/* Mobile adjustments */
@media (max-width: 768px) {
  .user-button {
    padding: 0.5rem;
    min-width: auto;
  }
  
  .user-info {
    display: none;
  }
  
  .user-dropdown {
    right: -1rem;
    left: -1rem;
    min-width: auto;
  }
  
  .dropdown-item {
    padding: 1rem;
    font-size: 1rem;
  }
  
  .item-icon {
    font-size: 1.25rem;
  }
}
</style>