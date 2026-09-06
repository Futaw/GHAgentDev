import type { ChatMessage } from '../../lib/types'

export type ChatState = {
  messages: ChatMessage[]
  status: 'idle' | 'sending' | 'streaming' | 'failed' | 'cancelled'
  error: string | null
}
export type ChatAction =
  | { type: 'loaded'; messages: ChatMessage[] }
  | { type: 'submitted'; user: ChatMessage; assistant: ChatMessage }
  | { type: 'started' }
  | { type: 'delta'; delta: string }
  | { type: 'completed' }
  | { type: 'failed'; message: string }
  | { type: 'cancelled' }

export const initialChatState: ChatState = { messages: [], status: 'idle', error: null }

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case 'loaded':
      return { ...state, messages: action.messages }
    case 'submitted':
      return { messages: [...state.messages, action.user, action.assistant], status: 'sending', error: null }
    case 'started':
      return { ...state, status: 'streaming' }
    case 'delta': {
      const messages = [...state.messages]
      const last = messages.at(-1)
      if (last?.role === 'assistant') messages[messages.length - 1] = { ...last, content: last.content + action.delta }
      return { ...state, messages }
    }
    case 'completed':
      return { ...state, status: 'idle', error: null }
    case 'failed':
      return { ...state, status: 'failed', error: action.message }
    case 'cancelled':
      return { ...state, status: 'cancelled', error: null }
  }
}
