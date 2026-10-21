import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface User {
  user_id:   number
  email:     string
  full_name: string
  role:      string
}

interface AuthState {
  token:        string | null
  refreshToken: string | null
  user:         User   | null
  setAuth:      (token: string, refresh: string, user: User) => void
  logout:       () => void
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token:        null,
      refreshToken: null,
      user:         null,

      setAuth: (token, refreshToken, user) => {
        localStorage.setItem('access_token',  token)
        localStorage.setItem('refresh_token', refreshToken)
        set({ token, refreshToken, user })
      },

      logout: () => {
        localStorage.removeItem('access_token')
        localStorage.removeItem('refresh_token')
        set({ token: null, refreshToken: null, user: null })
      },
    }),
    {
      name:    'cc-auth',
      partialize: (state) => ({
        token:        state.token,
        refreshToken: state.refreshToken,
        user:         state.user,
      }),
    }
  )
)
