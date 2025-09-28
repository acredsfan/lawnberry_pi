export interface User {
  id: string
  username: string
  email?: string
  role: 'admin' | 'user' | 'guest'
  created_at: string
  last_login?: string
}

export interface LoginCredentials {
  username: string
  password: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface RefreshResponse {
  access_token: string
  token_type: string
  expires_in: number
}