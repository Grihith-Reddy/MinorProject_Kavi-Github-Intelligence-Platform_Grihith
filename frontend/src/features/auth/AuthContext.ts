import { createContext } from 'react'

export interface AuthUser {
  sub: string
  email?: string | null
  name?: string | null
  picture?: string | null
}

export interface AuthContextValue {
  isAuthenticated: boolean
  isLoading: boolean
  user: AuthUser | null
  login: (returnTo?: string) => Promise<void>
  logout: () => Promise<void>
  getToken: () => Promise<string | undefined>
}

export const AuthContext = createContext<AuthContextValue | null>(null)
