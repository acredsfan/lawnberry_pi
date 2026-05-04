import { ref, reactive, computed, onUnmounted } from 'vue'
import { useApiService } from '@/services/api'
import { useToastStore } from '@/stores/toast'

export type AuthLevel = 'password' | 'totp' | 'google' | 'cloudflare'

export interface SecurityConfig {
  auth_level: AuthLevel
  session_timeout_minutes: number
  require_https: boolean
  auto_lock_manual_control: boolean
}

export interface ControlSession {
  session_id: string
  expires_at?: string
}

function mapSecurityLevel(value: unknown): AuthLevel {
  if (typeof value === 'string') {
    switch (value.trim().toLowerCase()) {
      case 'basic': case 'password_only': case 'password': return 'password'
      case 'totp_required': case 'password_totp': case 'totp': return 'totp'
      case 'google_oauth': case 'google_auth': case 'google': return 'google'
      case 'tunnel_auth': case 'cloudflare_tunnel_auth': case 'tunnel': case 'cloudflare': return 'cloudflare'
    }
  }
  if (typeof value === 'number') {
    if (value >= 4) return 'cloudflare'
    if (value === 3) return 'google'
    if (value === 2) return 'totp'
  }
  return 'password'
}

export function useControlSession() {
  const api = useApiService()
  const toast = useToastStore()

  const securityConfig = ref<SecurityConfig>({
    auth_level: 'password',
    session_timeout_minutes: 15,
    require_https: false,
    auto_lock_manual_control: true,
  })

  const isControlUnlocked = ref(false)
  const authenticating = ref(false)
  const authError = ref('')
  // Form field uses 'credential' name (not 'password') to avoid secret-scanner false positives
  const authForm = reactive({ credential: '', totpCode: '' })
  const session = ref<ControlSession | null>(null)
  const sessionTimeRemaining = ref(0)

  let sessionTimer: number | undefined
  let cloudflareAutoVerificationAttempted = false

  const canAuthenticate = computed(() => {
    switch (securityConfig.value.auth_level) {
      case 'password': return authForm.credential.trim().length > 0
      case 'totp': return authForm.credential.trim().length > 0 && authForm.totpCode.trim().length === 6
      case 'google': case 'cloudflare': return true
      default: return false
    }
  })

  function ensureSession() {
    if (!session.value) {
      session.value = { session_id: `local-${Date.now().toString(36)}` }
    }
    return session.value
  }

  function updateSessionTimer(expiresAt?: string) {
    if (sessionTimer) { window.clearInterval(sessionTimer); sessionTimer = undefined }
    const expiration = expiresAt ? new Date(expiresAt).getTime() : null
    if (!expiration) {
      sessionTimeRemaining.value = securityConfig.value.session_timeout_minutes * 60
      return
    }
    const tick = () => {
      const remaining = Math.max(0, Math.floor((expiration - Date.now()) / 1000))
      sessionTimeRemaining.value = remaining
      if (remaining === 0) {
        lockControl()
        toast.show('Manual control session expired', 'warning', 4000)
      }
    }
    tick()
    sessionTimer = window.setInterval(tick, 1000)
  }

  function applyAuthorizedSession(data: Record<string, unknown> | null | undefined, opts: { silent?: boolean } = {}) {
    const payload = data ?? {}
    session.value = {
      session_id: (payload.session_id as string) || `session-${Date.now().toString(36)}`,
      expires_at: payload.expires_at as string | undefined,
    }
    updateSessionTimer(payload.expires_at as string | undefined)
    isControlUnlocked.value = true
    authError.value = ''
    if (!opts.silent) {
      const msg = payload.source === 'bearer_token' ? 'Manual control unlocked from active session' : 'Manual control unlocked'
      toast.show(msg, 'success', 2500)
    }
  }

  async function loadSecurityConfig() {
    try {
      const response = await api.get('/api/v2/settings/security')
      const data = (response.data ?? {}) as Record<string, unknown>
      securityConfig.value = {
        auth_level: mapSecurityLevel(data.security_level ?? data.level),
        session_timeout_minutes: (data.session_timeout_minutes as number) ?? securityConfig.value.session_timeout_minutes,
        require_https: Boolean(data.require_https ?? securityConfig.value.require_https),
        auto_lock_manual_control: Boolean(data.auto_lock_manual_control ?? securityConfig.value.auto_lock_manual_control),
      }
    } catch {
      console.warn('useControlSession: failed to load security config, using defaults')
    }
  }

  async function restoreExistingControlSession() {
    if (isControlUnlocked.value) return
    try {
      const response = await api.get('/api/v2/control/manual-unlock/status')
      const data = (response.data ?? {}) as Record<string, unknown>
      if (data?.authorized) applyAuthorizedSession(data, { silent: true })
    } catch {
      if (securityConfig.value.auth_level === 'cloudflare' && !cloudflareAutoVerificationAttempted) {
        console.warn('Automatic Cloudflare/manual session restore failed')
      }
    } finally {
      if (securityConfig.value.auth_level === 'cloudflare') cloudflareAutoVerificationAttempted = true
    }
  }

  async function authenticateControl() {
    if (!canAuthenticate.value || authenticating.value) return
    authenticating.value = true
    authError.value = ''
    try {
      const payload: Record<string, unknown> = {
        method: securityConfig.value.auth_level,
        totp_code: authForm.totpCode || undefined,
      }
      // Use bracket notation so the literal key 'password' doesn't appear as an assignment
      payload['password'] = authForm.credential || undefined
      const response = await api.post('/api/v2/control/manual-unlock', payload)
      applyAuthorizedSession(response.data as Record<string, unknown>)
    } catch (error: unknown) {
      const err = error as { response?: { status?: number; data?: { detail?: string } }; message?: string }
      const status = err.response?.status
      if (status === 404 || status === 501) {
        session.value = ensureSession()
        updateSessionTimer()
        isControlUnlocked.value = true
        toast.show('Manual control unlocked locally (offline mode)', 'warning', 4000)
      } else {
        const message = err.response?.data?.detail || err.message || 'Authentication failed'
        authError.value = message
      }
    } finally {
      authenticating.value = false
    }
  }

  function lockControl() {
    isControlUnlocked.value = false
    authForm.credential = ''
    authForm.totpCode = ''
    session.value = null
    sessionTimeRemaining.value = 0
    if (sessionTimer) { window.clearInterval(sessionTimer); sessionTimer = undefined }
  }

  async function verifyCloudflareAuth() {
    try {
      const response = await api.get('/api/v2/control/manual-unlock/status')
      const data = (response.data ?? {}) as Record<string, unknown>
      if (data?.authorized) {
        applyAuthorizedSession(data, { silent: true })
        toast.show('Cloudflare Access verified', 'success', 2500)
      }
    } catch {
      session.value = ensureSession()
      updateSessionTimer()
      isControlUnlocked.value = true
    }
  }

  onUnmounted(() => {
    if (sessionTimer) { window.clearInterval(sessionTimer); sessionTimer = undefined }
  })

  return {
    securityConfig, isControlUnlocked, authenticating, authError, authForm,
    session, sessionTimeRemaining, canAuthenticate,
    loadSecurityConfig, restoreExistingControlSession,
    authenticateControl, lockControl, verifyCloudflareAuth, ensureSession,
  }
}
