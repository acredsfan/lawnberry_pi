import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import type { User, LoginCredentials, AuthResponse } from '@/types/auth'
import { authApi } from '@/composables/useApi'
import { registerAuthSessionCoordinator } from '@/services/authSessionCoordinator'

function readStoredUser(): User | null {
  try {
    const stored = localStorage.getItem('user_data')
    if (!stored) {
      return null
    }
    return JSON.parse(stored) as User
  } catch {
    localStorage.removeItem('user_data')
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(readStoredUser())
  const token = ref(localStorage.getItem('auth_token'))
  const tokenExpiry = ref<number | null>(
    localStorage.getItem('token_expiry') ? 
    parseInt(localStorage.getItem('token_expiry')!) : null
  )
  const isLoading = ref(false)
  const error = ref<string | null>(null)
  const lastActivity = ref<number>(Date.now())
  const expiryHandled = ref(false)
  let refreshTimer: number | null = null
  let refreshPromise: Promise<boolean> | null = null
  let cloudflareBootstrapPromise: Promise<boolean> | null = null

  const responseLifetimeMs = (expiresIn: number) => {
    const seconds = Number(expiresIn)
    return Number.isFinite(seconds) ? Math.max(0, seconds) * 1000 : 60 * 60 * 1000
  }

  const isAuthenticated = computed(() => {
    if (!token.value || !user.value) return false
    
    // Check if token is expired
    if (tokenExpiry.value && Date.now() > tokenExpiry.value) {
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

  const applyAuthResponse = (response: AuthResponse) => {
    token.value = response.access_token
    user.value = response.user
    const expiryTime = Date.now() + responseLifetimeMs(response.expires_in)
    tokenExpiry.value = expiryTime
    lastActivity.value = Date.now()
    localStorage.setItem('auth_token', response.access_token)
    localStorage.setItem('token_expiry', expiryTime.toString())
    localStorage.setItem('user_data', JSON.stringify(response.user))
  }

  const clearSession = () => {
    if (refreshTimer) {
      clearTimeout(refreshTimer)
      refreshTimer = null
    }
    user.value = null
    token.value = null
    tokenExpiry.value = null
    localStorage.removeItem('auth_token')
    localStorage.removeItem('token_expiry')
    localStorage.removeItem('user_data')
  }

  const login = async (credentials: LoginCredentials) => {
    try {
      isLoading.value = true
      error.value = null
      
      const response = await authApi.login(credentials)
      
      applyAuthResponse(response)
      
      // Start token refresh timer
      startTokenRefreshTimer(responseLifetimeMs(response.expires_in))
      
      return true
    } catch (err: any) {
      if (err?.response?.status === 429) {
        const retryHeader = err.response?.headers?.['retry-after']
        const retryAfter = retryHeader ? parseInt(retryHeader, 10) : undefined
        if (Number.isFinite(retryAfter) && retryAfter && retryAfter > 0) {
          error.value = `Too many attempts. Please try again in ${retryAfter} seconds.`
        } else {
          error.value = err.response?.data?.detail || 'Too many authentication attempts. Please wait and try again.'
        }
      } else {
        error.value = err.response?.data?.detail || err.message || 'Login failed'
      }
      return false
    } finally {
      isLoading.value = false
    }
  }

  const bootstrapCloudflare = async () => {
    if (isAuthenticated.value) return true
    if (cloudflareBootstrapPromise) return cloudflareBootstrapPromise

    cloudflareBootstrapPromise = (async () => {
      try {
        isLoading.value = true
        const response = await authApi.bootstrapCloudflare()
        applyAuthResponse(response)
        startTokenRefreshTimer(responseLifetimeMs(response.expires_in))
        return true
      } catch (err: any) {
        const status = err?.response?.status
        if (![401, 403].includes(status)) {
          console.warn('Cloudflare Access bootstrap unavailable:', err)
        }
        return false
      } finally {
        isLoading.value = false
      }
    })()

    try {
      return await cloudflareBootstrapPromise
    } finally {
      cloudflareBootstrapPromise = null
    }
  }

  const startTokenRefreshTimer = (issuedLifetimeMs?: number) => {
    // Clear existing timer
    if (refreshTimer) {
      clearTimeout(refreshTimer)
    }

    if (!tokenExpiry.value) return

    const remainingMs = tokenExpiry.value - Date.now()
    if (remainingMs <= 0) {
      clearSession()
      return
    }

    // Refresh after 80% of short-lived sessions and five minutes before
    // ordinary sessions. Timer setup never calls refresh synchronously: doing
    // so from inside refreshToken would await its own single-flight promise.
    const nominalLifetimeMs = Math.max(remainingMs, issuedLifetimeMs ?? remainingMs)
    const refreshLeadMs = issuedLifetimeMs === undefined
      ? 5 * 60 * 1000
      : Math.min(5 * 60 * 1000, Math.max(5 * 1000, nominalLifetimeMs * 0.2))
    let timeUntilRefresh = remainingMs - refreshLeadMs
    if (timeUntilRefresh <= 0) {
      timeUntilRefresh = Math.max(1000, remainingMs / 2)
    }
    refreshTimer = window.setTimeout(() => {
      refreshTimer = null
      void refreshToken()
    }, timeUntilRefresh)
  }

  const scheduleExpiryCleanup = () => {
    if (refreshTimer) clearTimeout(refreshTimer)
    if (!tokenExpiry.value) return
    const remainingMs = Math.max(0, tokenExpiry.value - Date.now())
    refreshTimer = window.setTimeout(() => {
      refreshTimer = null
      if (tokenExpiry.value !== null && Date.now() >= tokenExpiry.value) clearSession()
    }, remainingMs)
  }

  const logout = async () => {
    try {
      if (token.value) {
        await authApi.logout()
      }
    } catch (err) {
      console.warn('Logout request failed:', err)
    } finally {
      clearSession()
    }
  }

  const refreshToken = async () => {
    if (!token.value) return false
    if (refreshPromise) return refreshPromise

    refreshPromise = (async () => {
      try {
        const previousExpiry = tokenExpiry.value
        const response = await authApi.refresh()
        token.value = response.access_token
        const lifetimeMs = responseLifetimeMs(response.expires_in)
        const expiryTime = Date.now() + lifetimeMs
        tokenExpiry.value = expiryTime
        lastActivity.value = Date.now()
        localStorage.setItem('auth_token', response.access_token)
        localStorage.setItem('token_expiry', expiryTime.toString())
        // A Cloudflare-capped refresh may return the same absolute expiry.
        // Retrying immediately cannot extend trust and would create a loop;
        // retain the token only until that already-proven boundary.
        if (previousExpiry !== null && expiryTime <= previousExpiry + 1000) {
          scheduleExpiryCleanup()
        } else {
          startTokenRefreshTimer(lifetimeMs)
        }
        return true
      } catch (err) {
        console.warn('Token refresh failed:', err)
        clearSession()
        return false
      }
    })()

    try {
      return await refreshPromise
    } finally {
      refreshPromise = null
    }
  }

  const validateSession = async () => {
    try {
      if (!user.value && token.value) {
        user.value = readStoredUser()
      }

      if (!token.value) {
        // Try to restore from localStorage
        const storedToken = localStorage.getItem('auth_token')
        const storedExpiry = localStorage.getItem('token_expiry')
        const storedUser = readStoredUser()
        
        if (storedToken && storedExpiry && storedUser) {
          const expiryTime = parseInt(storedExpiry)
          
          // Check if token is still valid
          if (Date.now() < expiryTime) {
            token.value = storedToken
            tokenExpiry.value = expiryTime
            user.value = storedUser
            
            // Start refresh timer
            await startTokenRefreshTimer()
            
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

      if (token.value && user.value && tokenExpiry.value && Date.now() < tokenExpiry.value) {
        await startTokenRefreshTimer()
        return true
      }
      
      // Validate current token with server
      const userProfile = await authApi.getProfile()
      user.value = userProfile
      lastActivity.value = Date.now()
      
      return true
    } catch (err) {
      console.warn('Session validation failed:', err)
      clearSession()
      return false
    }
  }

  const updateActivity = () => {
    lastActivity.value = Date.now()
  }

  watch([token, tokenExpiry], ([tok, expiry]) => {
    if (tok && expiry && Date.now() > expiry) {
      if (!expiryHandled.value) {
        console.warn('Token has expired')
        expiryHandled.value = true
        clearSession()
      }
    } else {
      expiryHandled.value = false
    }
  }, { immediate: true })

  registerAuthSessionCoordinator(
    async () => (await refreshToken()) ? token.value : null,
    clearSession,
  )

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
    bootstrapCloudflare,
    logout,
    clearSession,
    refreshToken,
    validateSession,
    updateActivity,
    startTokenRefreshTimer
  }
})
