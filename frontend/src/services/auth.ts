// Thin wrapper around the Pinia auth store for ease of testing and future expansion
import { useAuthStore } from '@/stores/auth'
import type { LoginCredentials } from '@/types/auth'

export const authService = {
  isAuthenticated(): boolean {
    const store = useAuthStore()
    return store.isAuthenticated
  },
  async login(credentials: LoginCredentials): Promise<boolean> {
    const store = useAuthStore()
    return store.login(credentials)
  },
  async logout(): Promise<void> {
    const store = useAuthStore()
    await store.logout()
  },
  async validateSession(): Promise<boolean> {
    const store = useAuthStore()
    return store.validateSession()
  },
}
