import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, LoginCredentials } from '@/types/auth'
import { authApi } from '@/composables/useApi'

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const token = ref<string | null>(localStorage.getItem('auth_token'))
  const tokenExpiry = ref<number | null>(
    localStorage.getItem('token_expiry') ? 
    parseInt(localStorage.getItem('token_expiry')!) : null
  )
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const lastActivity = ref<number>(Date.now())

  const isAuthenticated = computed(() => {
    if (!token.value || !user.value) return false
    
    // Check if token is expired
    if (tokenExpiry.value && Date.now() > tokenExpiry.value) {
      console.warn('Token has expired')
      return false
    }
    
    return true
  })

  const timeUntilExpiry = computed(() => {
    if (!tokenExpiry.value) return null
    return Math.max(0, tokenExpiry.value - Date.now())
  })

  const isTokenExpiringSoon = computed(() => {
    const timeLeft = timeUntilExpiry.value
    return timeLeft !== null && timeLeft < 5 * 60 * 1000 // 5 minutes
  })

  const login = async (credentials: LoginCredentials) => {
    try {
      isLoading.value = true
      error.value = null
      
      const response = await authApi.login(credentials)
      
      token.value = response.access_token
      user.value = response.user
      
      // Calculate token expiry (assuming 1 hour if not provided)
      const expiryTime = Date.now() + (response.expires_in * 1000 || 60 * 60 * 1000)
      tokenExpiry.value = expiryTime
      lastActivity.value = Date.now()
      
      // Store in localStorage
      localStorage.setItem('auth_token', response.access_token)
      localStorage.setItem('token_expiry', expiryTime.toString())
      localStorage.setItem('user_data', JSON.stringify(response.user))
      
      // Start token refresh timer
      startTokenRefreshTimer()
      
      return true
    } catch (err: any) {
      error.value = err.response?.data?.detail || err.message || 'Login failed'
      return false
    } finally {
      isLoading.value = false
    }
  }

  let refreshTimer: number | null = null

  const startTokenRefreshTimer = () => {
    // Clear existing timer
    if (refreshTimer) {
      clearTimeout(refreshTimer)
    }
    
    if (!tokenExpiry.value) return
    
    // Refresh token 5 minutes before expiry
    const refreshTime = tokenExpiry.value - Date.now() - (5 * 60 * 1000)
    
    if (refreshTime > 0) {
      refreshTimer = window.setTimeout(async () => {
        try {
          await refreshToken()
        } catch (error) {
          console.error('Token refresh failed:', error)
          await logout()
        }
      }, refreshTime)
    }
  }

  const logout = async () => {
    try {
      if (token.value) {
        await authApi.logout()
      }
    } catch (err) {
      console.warn('Logout request failed:', err)
    } finally {
      // Clear timer
      if (refreshTimer) {
        clearTimeout(refreshTimer)
        refreshTimer = null
      }
      
      // Clear state
      user.value = null
      token.value = null
      tokenExpiry.value = null
      
      // Clear localStorage
      localStorage.removeItem('auth_token')
      localStorage.removeItem('token_expiry')
      localStorage.removeItem('user_data')
    }
  }

  const refreshToken = async () => {
    try {
      if (!token.value) return false
      
      const response = await authApi.refresh()
      token.value = response.access_token
      
      // Update expiry time
      const expiryTime = Date.now() + (response.expires_in * 1000 || 60 * 60 * 1000)
      tokenExpiry.value = expiryTime
      lastActivity.value = Date.now()
      
      // Update localStorage
      localStorage.setItem('auth_token', response.access_token)
      localStorage.setItem('token_expiry', expiryTime.toString())
      
      // Restart timer for next refresh
      startTokenRefreshTimer()
      
      return true
    } catch (err) {
      console.warn('Token refresh failed:', err)
      await logout()
      return false
    }
  }

  const validateSession = async () => {
    try {
      if (!token.value) {
        // Try to restore from localStorage
        const storedToken = localStorage.getItem('auth_token')
        const storedExpiry = localStorage.getItem('token_expiry')
        const storedUser = localStorage.getItem('user_data')
        
        if (storedToken && storedExpiry && storedUser) {
          const expiryTime = parseInt(storedExpiry)
          
          // Check if token is still valid
          if (Date.now() < expiryTime) {
            token.value = storedToken
            tokenExpiry.value = expiryTime
            user.value = JSON.parse(storedUser)
            
            // Start refresh timer
            startTokenRefreshTimer()
            
            return true
          } else {
            // Token expired, clear storage
            localStorage.removeItem('auth_token')
            localStorage.removeItem('token_expiry')
            localStorage.removeItem('user_data')
          }
        }
        
        return false
      }
      
      // Validate current token with server
      const userProfile = await authApi.getProfile()
      user.value = userProfile
      lastActivity.value = Date.now()
      
      return true
    } catch (err) {
      console.warn('Session validation failed:', err)
      await logout()
      return false
    }
  }

  const updateActivity = () => {
    lastActivity.value = Date.now()
  }

  return {
    user,
    token,
    tokenExpiry,
    isLoading,
    error,
    lastActivity,
    isAuthenticated,
    timeUntilExpiry,
    isTokenExpiringSoon,
    login,
    logout,
    refreshToken,
    validateSession,
    updateActivity,
    startTokenRefreshTimer
  }
})