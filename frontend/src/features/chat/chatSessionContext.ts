import { createContext, useContext } from 'react'
import type { ProblemDetails } from '../../lib/api'
import type { ChatState } from './chatReducer'

export type SessionStatus = 'uninitialized' | 'preparing' | 'ready' | 'failed'
export type ProgressStage = 'submitting' | 'accepted' | 'running' | 'answering' | 'reconnecting'

export type ChatSessionContextValue = {
  sessionStatus: SessionStatus
  sessionError: ProblemDetails | null
  state: ChatState
  progressStage: ProgressStage | null
  progressStartedAt: number | null
  requestTraceId: string
  busy: boolean
  canCancel: boolean
  ensureSession: () => Promise<void>
  retrySession: () => Promise<void>
  submit: (content: string) => boolean
  cancel: () => Promise<void>
  retryLastMessage: () => boolean
}

export const ChatSessionContext = createContext<ChatSessionContextValue | null>(null)

export function useChatSession() {
  const context = useContext(ChatSessionContext)
  if (!context) throw new Error('useChatSession must be used within ChatSessionProvider')
  return context
}
