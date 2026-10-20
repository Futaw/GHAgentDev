import { FormEvent, useEffect, useRef, useState } from 'react'
import { type ProgressStage, useChatSession } from './chatSessionContext'

const progressLabels: Record<ProgressStage, string> = {
  submitting: '質問を送信しています',
  accepted: '質問を受け付けました',
  running: 'Codexが処理しています',
  answering: '回答を作成しています',
  reconnecting: '進捗表示へ再接続しています',
}

function useElapsedSeconds(startedAt: number | null) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (startedAt === null) {
      setElapsed(0)
      return
    }
    const update = () => setElapsed(Math.max(0, Math.floor((Date.now() - startedAt) / 1_000)))
    update()
    const timer = window.setInterval(update, 1_000)
    return () => window.clearInterval(timer)
  }, [startedAt])
  return elapsed
}

function formatElapsed(seconds: number) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, '0')
  return `${minutes}:${(seconds % 60).toString().padStart(2, '0')}`
}

export function ChatPage() {
  const [input, setInput] = useState('')
  const {
    sessionStatus,
    sessionError,
    state,
    progressStage,
    progressStartedAt,
    requestTraceId,
    busy,
    canCancel,
    ensureSession,
    retrySession,
    submit,
    cancel,
    retryLastMessage,
  } = useChatSession()
  const elapsed = useElapsedSeconds(progressStartedAt)
  const endRef = useRef<HTMLDivElement>(null)
  const isComposingRef = useRef(false)

  useEffect(() => {
    void ensureSession()
  }, [ensureSession])

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [state.messages, progressStage])

  const send = () => {
    if (!submit(input)) return false
    isComposingRef.current = false
    setInput('')
    return true
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    send()
  }

  return (
    <main className="chat-shell">
      <section className="chat-panel" aria-label="Codexとのチャット">
        <div className="chat-intro">
          <span className="eyebrow">READ-ONLY WORKSPACE</span>
          <h1>Codexとの接続を試す</h1>
          <p>この画面では、設定されたテスト用Workspaceについて読み取り専用で質問できます。</p>
        </div>
        <div className="messages" aria-live="polite" aria-busy={busy}>
          {sessionStatus === 'preparing' && <p className="muted">セッションを準備しています…</p>}
          {sessionStatus === 'failed' && sessionError && (
            <div className="error-card" role="alert">
              <p>{sessionError.detail}</p>
              {sessionError.trace_id && <small>トレースID: {sessionError.trace_id}</small>}
              <button type="button" onClick={() => void retrySession()}>再試行</button>
            </div>
          )}
          {state.messages.map((message) => (
            <article key={message.id} className={`message ${message.role}`}>
              <span>{message.role === 'user' ? 'あなた' : 'Codex'}</span>
              <p>{message.content}</p>
            </article>
          ))}
          {progressStage && progressStartedAt !== null && (
            <section className="progress-card" aria-label="Codexの処理状況">
              <div>
                <p className="progress-label" role="status" aria-live="polite">
                  <span aria-hidden="true" />{progressLabels[progressStage]}
                </p>
                <p className="elapsed" aria-live="off">経過時間 {formatElapsed(elapsed)}</p>
                {elapsed >= 30 && <p className="delay-note">通常より時間がかかっています。処理は継続中です。</p>}
              </div>
              {canCancel && <button type="button" className="stop" onClick={() => void cancel()}>中止</button>}
            </section>
          )}
          {state.error && (
            <div className="error-card" role="alert">
              <p>{state.error}</p>
              {requestTraceId && <small>トレースID: {requestTraceId}</small>}
              <button type="button" onClick={() => retryLastMessage()}>同じ内容を再送信</button>
            </div>
          )}
          <div ref={endRef} />
        </div>
        <form className="composer" onSubmit={handleSubmit}>
          <label htmlFor="chat-input" className="sr-only">Codexへの質問</label>
          <textarea
            id="chat-input"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onCompositionStart={() => {
              isComposingRef.current = true
            }}
            onCompositionEnd={() => {
              isComposingRef.current = false
            }}
            onKeyDown={(event) => {
              const isImeBoundary = event.nativeEvent.keyCode === 229
              const isImeInput = isComposingRef.current
                || event.nativeEvent.isComposing
                || isImeBoundary
              if (event.key !== 'Enter' || event.shiftKey || isImeInput) return
              if (send()) event.preventDefault()
            }}
            placeholder="このWorkspaceについて質問する"
            disabled={sessionStatus !== 'ready' || busy}
            rows={3}
          />
          <div className="composer-actions">
            <small>Enterで送信 · Shift + Enterで改行</small>
            <button type="submit" className="primary" disabled={!input.trim() || sessionStatus !== 'ready' || busy}>送信</button>
          </div>
        </form>
      </section>
    </main>
  )
}
