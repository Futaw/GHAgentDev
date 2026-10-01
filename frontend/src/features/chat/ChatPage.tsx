import { useMutation } from '@tanstack/react-query'
import { FormEvent, useEffect, useReducer, useRef, useState } from 'react'
import { api } from '../../lib/api'
import type { ChatMessage, ChatSession, TurnAccepted } from '../../lib/types'
import { chatReducer, initialChatState } from './chatReducer'

const newOptimisticMessage = (role: 'user' | 'assistant', content: string): ChatMessage => ({
  id: crypto.randomUUID(),
  role,
  content,
  status: role === 'assistant' ? 'streaming' : 'completed',
  created_at: new Date().toISOString(),
})

export function ChatPage() {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [input, setInput] = useState('')
  const [lastInput, setLastInput] = useState('')
  const [turn, setTurn] = useState<TurnAccepted | null>(null)
  const [streamState, setStreamState] = useState<'connected' | 'reconnecting'>('connected')
  const [state, dispatch] = useReducer(chatReducer, initialChatState)
  const endRef = useRef<HTMLDivElement>(null)
  const sessionRequestedRef = useRef(false)
  const createSession = useMutation({
    mutationFn: () => api<ChatSession>('/api/chat/sessions', { method: 'POST' }),
    onSuccess: (session) => setSessionId(session.id),
    onError: () => {
      sessionRequestedRef.current = false
    },
  })
  const send = useMutation({
    mutationFn: ({ id, content }: { id: string; content: string }) =>
      api<TurnAccepted>(`/api/chat/sessions/${id}/messages`, {
        method: 'POST',
        body: JSON.stringify({ content }),
      }),
    onSuccess: setTurn,
    onError: () => dispatch({ type: 'failed', message: 'メッセージを送信できませんでした。' }),
  })

  useEffect(() => {
    if (!sessionId && !sessionRequestedRef.current) {
      sessionRequestedRef.current = true
      createSession.mutate()
    }
  }, [createSession, sessionId])

  useEffect(() => {
    if (!turn) return
    const stream = new EventSource(turn.events_url)
    const onStarted = () => dispatch({ type: 'started' })
    const onDelta = (raw: Event) => {
      const data = JSON.parse((raw as MessageEvent).data) as { delta: string }
      dispatch({ type: 'delta', delta: data.delta })
    }
    const onCompleted = () => {
      dispatch({ type: 'completed' })
      setTurn(null)
      stream.close()
    }
    const onFailed = (raw: Event) => {
      const data = JSON.parse((raw as MessageEvent).data) as { message: string }
      dispatch({ type: 'failed', message: data.message })
      setTurn(null)
      stream.close()
    }
    const onCancelled = () => {
      dispatch({ type: 'cancelled' })
      setTurn(null)
      stream.close()
    }
    stream.addEventListener('turn.started', onStarted)
    stream.addEventListener('message.delta', onDelta)
    stream.addEventListener('turn.completed', onCompleted)
    stream.addEventListener('turn.failed', onFailed)
    stream.addEventListener('turn.cancelled', onCancelled)
    stream.onopen = () => setStreamState('connected')
    stream.onerror = () => setStreamState('reconnecting')
    return () => stream.close()
  }, [turn])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [state.messages])

  const submit = (event?: FormEvent, retryText?: string) => {
    event?.preventDefault()
    const content = (retryText ?? input).trim()
    if (!content || !sessionId || turn || send.isPending) return
    setLastInput(content)
    setInput('')
    dispatch({
      type: 'submitted',
      user: newOptimisticMessage('user', content),
      assistant: newOptimisticMessage('assistant', ''),
    })
    send.mutate({ id: sessionId, content })
  }

  const cancel = async () => {
    if (!turn) return
    await api(`/api/turns/${turn.turn_id}/cancel`, { method: 'POST' })
  }

  const busy = state.status === 'sending' || state.status === 'streaming'

  return (
    <main className="chat-shell">
      <section className="chat-panel" aria-label="Codexとのチャット">
        <div className="chat-intro">
          <span className="eyebrow">READ-ONLY WORKSPACE</span>
          <h1>Codexとの接続を試す</h1>
          <p>この画面では、設定されたテスト用Workspaceについて読み取り専用で質問できます。</p>
        </div>
        <div className="messages" aria-live="polite" aria-busy={busy}>
          {createSession.isPending && <p className="muted">セッションを準備しています…</p>}
          {createSession.isError && (
            <div className="error-card"><p>セッションを開始できませんでした。</p><button onClick={() => {
              sessionRequestedRef.current = true
              createSession.mutate()
            }}>再試行</button></div>
          )}
          {state.messages.map((message) => (
            <article key={message.id} className={`message ${message.role}`}>
              <span>{message.role === 'user' ? 'あなた' : 'Codex'}</span>
              <p>{message.content || (message.status === 'streaming' ? '考えています…' : '')}</p>
            </article>
          ))}
          {streamState === 'reconnecting' && busy && <p className="stream-note">ストリームへ再接続しています…</p>}
          {state.error && (
            <div className="error-card" role="alert">
              <p>{state.error}</p>
              <button onClick={() => submit(undefined, lastInput)}>同じ内容を再送信</button>
            </div>
          )}
          <div ref={endRef} />
        </div>
        <form className="composer" onSubmit={submit}>
          <label htmlFor="chat-input" className="sr-only">Codexへの質問</label>
          <textarea
            id="chat-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) submit(event)
            }}
            placeholder="このWorkspaceについて質問する"
            disabled={!sessionId || busy}
            rows={3}
          />
          <div className="composer-actions">
            <small>Enterで送信 · Shift + Enterで改行</small>
            {busy && turn ? (
              <button type="button" className="stop" onClick={() => void cancel()}>中止</button>
            ) : (
              <button type="submit" className="primary" disabled={!input.trim() || !sessionId}>送信</button>
            )}
          </div>
        </form>
      </section>
    </main>
  )
}
