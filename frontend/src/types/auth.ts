export interface User {
  id: string
  username: string
  email?: string
  role: 'admin' | 'operator' | 'user' | 'guest'
  created_at: string
  last_login?: string
}

export type LoginCredentials =
  | { credential: string; username?: never; password?: never }
  | { credential?: never; username: string; password: string }

export interface AuthResponse {
  access_token: string
  token?: string
  token_type: string
  expires_in: number
  expires_at?: string
  user: User
}

export interface RefreshResponse {
  access_token: string
  token?: string
  token_type: string
  expires_in: number
  expires_at?: string
}
