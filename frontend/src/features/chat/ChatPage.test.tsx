import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
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
  status: 'running',
  events_url: '/api/turns/turn-1/events',
}

class MockEventSource {
  onopen: ((event: Event) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  addEventListener() {}

  close() {}
}

function renderChat() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  return render(
    <QueryClientProvider client={client}>
      <ChatSessionProvider>
        <ChatPage />
      </ChatSessionProvider>
    </QueryClientProvider>,
  )
}

function mockChatRequests() {
  return vi.spyOn(globalThis, 'fetch')
    .mockResolvedValueOnce(new Response(JSON.stringify(session), { status: 200 }))
    .mockResolvedValueOnce(new Response(JSON.stringify(turn), { status: 202 }))
}

async function getReadyInput() {
  const input = screen.getByLabelText('Codexへの質問')
  await waitFor(() => expect(input).toBeEnabled())
  return input
}

beforeEach(() => {
  vi.stubGlobal('EventSource', MockEventSource)
  Object.defineProperty(Element.prototype, 'scrollIntoView', {
    configurable: true,
    value: vi.fn(),
  })
})

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

describe('ChatPage input', () => {
  it('does not send when Enter confirms an active IME composition', async () => {
    const fetchMock = mockChatRequests()
    renderChat()
    const input = await getReadyInput()

    fireEvent.compositionStart(input)
    fireEvent.change(input, { target: { value: '登録処理' } })
    const defaultAllowed = fireEvent.keyDown(input, {
      key: 'Enter',
      isComposing: false,
      keyCode: 13,
    })

    expect(defaultAllowed).toBe(true)
    expect(input).toHaveValue('登録処理')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('あなた')).not.toBeInTheDocument()
  })

  it('does not send when the native key event is composing', async () => {
    const fetchMock = mockChatRequests()
    renderChat()
    const input = await getReadyInput()

    fireEvent.change(input, { target: { value: '登録処理' } })
    const defaultAllowed = fireEvent.keyDown(input, {
      key: 'Enter',
      isComposing: true,
      keyCode: 13,
    })

    expect(defaultAllowed).toBe(true)
    expect(input).toHaveValue('登録処理')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not send the composition boundary Enter reported with keyCode 229', async () => {
    const fetchMock = mockChatRequests()
    renderChat()
    const input = await getReadyInput()

    fireEvent.compositionStart(input)
    fireEvent.change(input, { target: { value: '登録処理' } })
    fireEvent.compositionEnd(input)
    const defaultAllowed = fireEvent.keyDown(input, {
      key: 'Enter',
      isComposing: false,
      keyCode: 229,
    })

    expect(defaultAllowed).toBe(true)
    expect(input).toHaveValue('登録処理')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('sends once on a regular Enter after composition ends', async () => {
    const fetchMock = mockChatRequests()
    renderChat()
    const input = await getReadyInput()

    fireEvent.compositionStart(input)
    fireEvent.change(input, { target: { value: '登録処理を説明してください' } })
    fireEvent.compositionEnd(input)
    const defaultAllowed = fireEvent.keyDown(input, {
      key: 'Enter',
      isComposing: false,
      keyCode: 13,
    })

    expect(defaultAllowed).toBe(false)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/chat/sessions/session-1/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ content: '登録処理を説明してください' }),
      }),
    )
    expect(input).toHaveValue('')
    expect(screen.getByText('登録処理を説明してください')).toBeInTheDocument()
    expect(screen.getAllByText('あなた')).toHaveLength(1)
  })

  it('keeps Shift + Enter as an unhandled newline operation', async () => {
    const fetchMock = mockChatRequests()
    renderChat()
    const input = await getReadyInput()

    fireEvent.change(input, { target: { value: '1行目' } })
    const defaultAllowed = fireEvent.keyDown(input, {
      key: 'Enter',
      shiftKey: true,
      keyCode: 13,
    })

    expect(defaultAllowed).toBe(true)
    expect(input).toHaveValue('1行目')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('sends from the explicit send button', async () => {
    const user = userEvent.setup()
    const fetchMock = mockChatRequests()
    renderChat()
    const input = await getReadyInput()

    await user.type(input, '送信ボタンから質問します')
    fireEvent.compositionStart(input)
    await user.click(screen.getByRole('button', { name: '送信' }))

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    expect(fetchMock).toHaveBeenLastCalledWith(
      '/api/chat/sessions/session-1/messages',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ content: '送信ボタンから質問します' }),
      }),
    )
  })
})
