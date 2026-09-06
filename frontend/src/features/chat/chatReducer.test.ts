import { describe, expect, it } from 'vitest'
import { chatReducer, initialChatState } from './chatReducer'

const message = (role: 'user' | 'assistant', content: string) => ({
  id: role,
  role,
  content,
  status: 'completed',
  created_at: '2026-09-06T00:00:00Z',
})
describe('chatReducer', () => {
  it('appends streamed deltas in order', () => {
    let state = chatReducer(initialChatState, {
      type: 'submitted',
      user: message('user', '質問'),
      assistant: message('assistant', ''),
    })
    state = chatReducer(state, { type: 'delta', delta: '最初' })
    state = chatReducer(state, { type: 'delta', delta: 'の回答' })
    expect(state.messages.at(-1)?.content).toBe('最初の回答')
  })

  it('keeps a recoverable error state after failure', () => {
    const state = chatReducer(initialChatState, { type: 'failed', message: '失敗しました' })
    expect(state.status).toBe('failed')
    expect(state.error).toBe('失敗しました')
  })
})
