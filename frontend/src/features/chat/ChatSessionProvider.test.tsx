import { StrictMode, useState } from 'react'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ChatPage } from './ChatPage'
import { ChatSessionProvider } from './ChatSessionProvider'

const session = {
  id: 'session-1',
  status: 'idle',
  created_at: '2026-10-18T00:00:00Z',
}

const turn = {
  turn_id: 'turn-1',
  status: 'queued',
  events_url: '/api/turns/turn-1/events',
}

class ControllableEventSource {
  static instances: ControllableEventSource[] = []
  onopen: ((event: Event) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  listeners = new Map<string, (event: Event) => void>()
  close = vi.fn()

  constructor(readonly url: string) {
    ControllableEventSource.instances.push(this)
  }

  addEventListener(type: string, listener: EventListenerOrEventListenerObject) {
    this.listeners.set(type, listener as (event: Event) => void)
  }

  emit(type: string, data: object = {}) {
    this.listeners.get(type)?.(new MessageEvent(type, { data: JSON.stringify(data) }))
  }
}

function response(body: object, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': status >= 400 ? 'application/problem+json' : 'application/json' },
  })
}

function Harness() {
  const [page, setPage] = useState<'chat' | 'repositories'>('chat')
  return (
    <>
      <button onClick={() => setPage('chat')}>Chatへ</button>
      <button onClick={() => setPage('repositories')}>Repositoriesへ</button>
      {page === 'chat' ? <ChatPage /> : <main>Repository一覧</main>}
    </>
  )
}

beforeEach(() => {
  ControllableEventSource.instances = []
  vi.stubGlobal('EventSource', ControllableEventSource)
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  })
})

afterEach(() => {
  vi.useRealTimers()
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('ChatSessionProvider', () => {
  it('creates only one session under StrictMode', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(response(session))

    render(
      <StrictMode>
        <ChatSessionProvider><ChatPage /></ChatSessionProvider>
      </StrictMode>,
    )

    await waitFor(() => expect(screen.getByLabelText('Codexへの質問')).toBeEnabled())
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('stops after a session error and retries only when requested', async () => {
    const problem = {
      title: 'Unavailable',
      detail: 'Codex App Serverへ接続できません。',
      status: 503,
      code: 'CODEX_UNAVAILABLE',
      retryable: true,
      trace_id: 'trace-503',
    }
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response(problem, 503))
      .mockResolvedValueOnce(response(session))

    render(<ChatSessionProvider><ChatPage /></ChatSessionProvider>)

    expect(await screen.findByText(problem.detail)).toBeInTheDocument()
    expect(screen.getByText('トレースID: trace-503')).toBeInTheDocument()
    await new Promise((resolve) => window.setTimeout(resolve, 20))
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await userEvent.click(screen.getByRole('button', { name: '再試行' }))
    await waitFor(() => expect(screen.getByLabelText('Codexへの質問')).toBeEnabled())
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('keeps messages and the event stream while navigating between child pages', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response(session))
      .mockResolvedValueOnce(response(turn, 202))

    render(<ChatSessionProvider><Harness /></ChatSessionProvider>)
    const input = await screen.findByLabelText('Codexへの質問')
    await waitFor(() => expect(input).toBeEnabled())
    fireEvent.change(input, { target: { value: '登録処理を説明してください' } })
    await userEvent.click(screen.getByRole('button', { name: '送信' }))

    await screen.findByText('質問を受け付けました')
    const stream = ControllableEventSource.instances[0]
    act(() => {
      stream.emit('turn.started')
      stream.emit('message.delta', { delta: '回答の途中' })
    })
    await screen.findByText('回答を作成しています')

    await userEvent.click(screen.getByRole('button', { name: 'Repositoriesへ' }))
    expect(screen.getByText('Repository一覧')).toBeInTheDocument()
    expect(stream.close).not.toHaveBeenCalled()

    await userEvent.click(screen.getByRole('button', { name: 'Chatへ' }))
    expect(screen.getByText('登録処理を説明してください')).toBeInTheDocument()
    expect(screen.getByText('回答の途中')).toBeInTheDocument()
    expect(screen.getByText('回答を作成しています')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('shows reconnecting state without discarding the active turn', async () => {
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response(session))
      .mockResolvedValueOnce(response(turn, 202))

    render(<ChatSessionProvider><ChatPage /></ChatSessionProvider>)
    const input = await screen.findByLabelText('Codexへの質問')
    await waitFor(() => expect(input).toBeEnabled())
    fireEvent.change(input, { target: { value: '質問' } })
    await userEvent.click(screen.getByRole('button', { name: '送信' }))
    await waitFor(() => expect(ControllableEventSource.instances).toHaveLength(1))

    act(() => ControllableEventSource.instances[0].onerror?.(new Event('error')))
    expect(await screen.findByText('進捗表示へ再接続しています')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '中止' })).toBeInTheDocument()
  })

  it('shows each progress stage, delayed guidance, and enables input after completion', async () => {
    let resolveTurn!: (value: Response) => void
    const turnResponse = new Promise<Response>((resolve) => {
      resolveTurn = resolve
    })
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(response(session))
      .mockReturnValueOnce(turnResponse)

    render(<ChatSessionProvider><ChatPage /></ChatSessionProvider>)
    const input = await screen.findByLabelText('Codexへの質問')
    await waitFor(() => expect(input).toBeEnabled())

    const startedAt = new Date('2026-10-20T00:00:00Z').getTime()
    vi.useFakeTimers()
    vi.setSystemTime(startedAt)
    fireEvent.change(input, { target: { value: '進捗を確認する' } })
    fireEvent.click(screen.getByRole('button', { name: '送信' }))

    expect(screen.getByText('質問を送信しています')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '中止' })).not.toBeInTheDocument()

    await act(async () => {
      resolveTurn(response(turn, 202))
      await turnResponse
    })
    expect(screen.getByText('質問を受け付けました')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '中止' })).toBeInTheDocument()

    const stream = ControllableEventSource.instances[0]
    act(() => stream.emit('turn.started'))
    expect(screen.getByText('Codexが処理しています')).toBeInTheDocument()
    act(() => stream.emit('message.delta', { delta: '回答' }))
    expect(screen.getByText('回答を作成しています')).toBeInTheDocument()

    vi.setSystemTime(startedAt + 30_000)
    act(() => vi.advanceTimersByTime(1_000))
    expect(screen.getByText('経過時間 00:31')).toBeInTheDocument()
    expect(screen.getByText('通常より時間がかかっています。処理は継続中です。')).toBeInTheDocument()

    act(() => stream.emit('turn.completed'))
    expect(input).toBeEnabled()
    expect(screen.queryByLabelText('Codexの処理状況')).not.toBeInTheDocument()
  })
})
