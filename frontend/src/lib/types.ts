export type AuthStatus = {
  status: 'checking' | 'unauthenticated' | 'authenticating' | 'authenticated' | 'expired' | 'error'
  auth_mode: string | null
  plan_type: string | null
  app_server_connected: boolean
}
export type Health = {
  status: string
  http_server: boolean
  app_server_connected: boolean
  app_server_error: string | null
}

export type ChatSession = {
  id: string
  status: 'idle' | 'running'
  created_at: string
}

export type ChatMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  status: string
  created_at: string
}

export type TurnAccepted = {
  turn_id: string
  status: string
  events_url: string
}
