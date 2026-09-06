import { api } from '../../lib/api'
import type { AuthStatus } from '../../lib/types'

export const getAuthStatus = () => api<AuthStatus>('/api/auth/status')

export const startLogin = () =>
  api<{ login_id: string; auth_url: string }>('/api/auth/login', { method: 'POST' })

export const cancelLogin = (loginId: string) =>
  api<void>(`/api/auth/login/${encodeURIComponent(loginId)}/cancel`, { method: 'POST' })
