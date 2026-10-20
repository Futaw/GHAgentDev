import {
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from 'react'
import { api, ApiError, type ProblemDetails } from '../../lib/api'
import type { ChatMessage, ChatSession, TurnAccepted } from '../../lib/types'
import { chatReducer, initialChatState } from './chatReducer'
import {
  ChatSessionContext,
  type ChatSessionContextValue,
  type ProgressStage,
  type SessionStatus,
} from './chatSessionContext'

const newOptimisticMessage = (role: 'user' | 'assistant', content: string): ChatMessage => ({
  id: crypto.randomUUID(),
  role,
  content,
  status: role === 'assistant' ? 'streaming' : 'completed',
  created_at: new Date().toISOString(),
})

function problemFrom(error: unknown, fallback: string): ProblemDetails {
  if (error instanceof ApiError) return error.problem
  return {
    title: 'Request failed',
    detail: fallback,
    status: 0,
    code: 'UNKNOWN_ERROR',
    retryable: true,
    trace_id: '',
  }
}

export function ChatSessionProvider({ children }: { children: ReactNode }) {
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>('uninitialized')
  const [sessionError, setSessionError] = useState<ProblemDetails | null>(null)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [turn, setTurn] = useState<TurnAccepted | null>(null)
  const [state, dispatch] = useReducer(chatReducer, initialChatState)
  const [progressStage, setProgressStage] = useState<ProgressStage | null>(null)
  const [progressStartedAt, setProgressStartedAt] = useState<number | null>(null)
  const [requestTraceId, setRequestTraceId] = useState('')
  const statusRef = useRef<SessionStatus>('uninitialized')
  const sessionPromiseRef = useRef<Promise<void> | null>(null)
  const lastInputRef = useRef('')
  const messageRequestPendingRef = useRef(false)
  const activeStageRef = useRef<Exclude<ProgressStage, 'reconnecting'>>('accepted')

  const createSession = useCallback(async (allowRetry: boolean) => {
    if (statusRef.current === 'ready' || statusRef.current === 'preparing') {
      return sessionPromiseRef.current ?? Promise.resolve()
    }
    if (statusRef.current === 'failed' && !allowRetry) return

    statusRef.current = 'preparing'
    setSessionStatus('preparing')
    setSessionError(null)
    const request = api<ChatSession>('/api/chat/sessions', { method: 'POST' })
      .then((session) => {
        setSessionId(session.id)
        statusRef.current = 'ready'
        setSessionStatus('ready')
      })
      .catch((error: unknown) => {
        statusRef.current = 'failed'
        setSessionStatus('failed')
        setSessionError(problemFrom(error, 'セッションを開始できませんでした。'))
      })
      .finally(() => {
        sessionPromiseRef.current = null
      })
    sessionPromiseRef.current = request
    return request
  }, [])

  const ensureSession = useCallback(() => createSession(false), [createSession])
  const retrySession = useCallback(() => createSession(true), [createSession])

  useEffect(() => {
    if (!turn) return
    const stream = new EventSource(turn.events_url)
    const onStarted = () => {
      dispatch({ type: 'started' })
      activeStageRef.current = 'running'
      setProgressStage('running')
    }
    const onDelta = (raw: Event) => {
      const data = JSON.parse((raw as MessageEvent).data) as { delta: string }
      dispatch({ type: 'delta', delta: data.delta })
      activeStageRef.current = 'answering'
      setProgressStage('answering')
    }
    const finish = () => {
      setTurn(null)
      setProgressStage(null)
      setProgressStartedAt(null)
      stream.close()
    }
    const onCompleted = () => {
      dispatch({ type: 'completed' })
      finish()
    }
    const onFailed = (raw: Event) => {
      const data = JSON.parse((raw as MessageEvent).data) as { message: string }
      dispatch({ type: 'failed', message: data.message })
      finish()
    }
    const onCancelled = () => {
      dispatch({ type: 'cancelled' })
      finish()
    }
    stream.addEventListener('turn.started', onStarted)
    stream.addEventListener('message.delta', onDelta)
    stream.addEventListener('turn.completed', onCompleted)
    stream.addEventListener('turn.failed', onFailed)
    stream.addEventListener('turn.cancelled', onCancelled)
    stream.onopen = () => setProgressStage(activeStageRef.current)
    stream.onerror = () => setProgressStage('reconnecting')
    return () => stream.close()
  }, [turn])

  const submit = useCallback((rawContent: string) => {
    const content = rawContent.trim()
    if (!content || !sessionId || turn || messageRequestPendingRef.current
      || ['submitting', 'queued', 'running'].includes(state.status)) {
      return false
    }
    messageRequestPendingRef.current = true
    lastInputRef.current = content
    setRequestTraceId('')
    dispatch({
      type: 'submitted',
      user: newOptimisticMessage('user', content),
      assistant: newOptimisticMessage('assistant', ''),
    })
    activeStageRef.current = 'submitting'
    setProgressStage('submitting')
    setProgressStartedAt(Date.now())
    void api<TurnAccepted>(`/api/chat/sessions/${sessionId}/messages`, {
      method: 'POST',
      body: JSON.stringify({ content }),
    }).then((accepted) => {
      messageRequestPendingRef.current = false
      dispatch({ type: 'accepted' })
      activeStageRef.current = 'accepted'
      setProgressStage('accepted')
      setTurn(accepted)
    }).catch((error: unknown) => {
      messageRequestPendingRef.current = false
      const problem = problemFrom(error, 'メッセージを送信できませんでした。')
      dispatch({ type: 'failed', message: problem.detail })
      setRequestTraceId(problem.trace_id)
      setProgressStage(null)
      setProgressStartedAt(null)
    })
    return true
  }, [sessionId, state.status, turn])

  const cancel = useCallback(async () => {
    if (!turn) return
    try {
      await api(`/api/turns/${turn.turn_id}/cancel`, { method: 'POST' })
    } catch (error: unknown) {
      const problem = problemFrom(error, '処理を中止できませんでした。')
      dispatch({ type: 'failed', message: problem.detail })
      setRequestTraceId(problem.trace_id)
      setProgressStage(null)
      setProgressStartedAt(null)
      setTurn(null)
    }
  }, [turn])

  const busy = ['submitting', 'queued', 'running'].includes(state.status)
  const value = useMemo<ChatSessionContextValue>(() => ({
    sessionStatus,
    sessionError,
    state,
    progressStage,
    progressStartedAt,
    requestTraceId,
    busy,
    canCancel: turn !== null,
    ensureSession,
    retrySession,
    submit,
    cancel,
    retryLastMessage: () => submit(lastInputRef.current),
  }), [
    busy, cancel, ensureSession, progressStage, progressStartedAt, requestTraceId,
    retrySession, sessionError, sessionStatus, state, submit, turn,
  ])

  return <ChatSessionContext.Provider value={value}>{children}</ChatSessionContext.Provider>
}
