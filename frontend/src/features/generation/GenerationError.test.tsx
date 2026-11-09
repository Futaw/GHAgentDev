import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { ViewerCreatePage } from '../viewers/ViewerCreatePage'
import { GenerationJobPage } from './GenerationJobPage'

const options = {
  document_types: [{ value: 'functional_spec', label: '仕様書' }],
  detail_levels: [{ value: 'standard', label: '標準' }],
  target_audiences: [{ value: 'engineer', label: '開発者' }],
  themes: [{ value: 'technical-light', label: 'Light' }],
  densities: [{ value: 'comfortable', label: 'Comfortable' }],
}
function mount(page: 'create' | 'job') {
  // Even a globally retrying QueryClient must not repeat generation POSTs.
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: 3, retryDelay: 1 } } })
  render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[page === 'create' ? '/repositories/repo/viewers/new' : '/jobs/job']}><Routes>
    <Route path="/repositories/:repositoryId/viewers/new" element={<ViewerCreatePage />} />
    <Route path="/jobs/:jobId" element={<GenerationJobPage />} />
  </Routes></MemoryRouter></QueryClientProvider>)
}
afterEach(() => { cleanup(); vi.restoreAllMocks() })

it.each([
  ['completed', 'Viewerの生成が完了しました'],
  ['failed', 'Viewerの生成に失敗しました'],
  ['cancelled', 'Viewerの生成を中止しました'],
])('uses the terminal %s heading and hides the stop action', async (status, title) => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
    id: 'job', status, current_phase: 'analyzing_repository', viewer_id: null, error: null,
  }), { status: 200 }))
  mount('job')
  expect(await screen.findByRole('heading', { name: title })).toBeInTheDocument()
  expect(screen.queryByRole('heading', { name: 'Viewerを生成中' })).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '中止' })).not.toBeInTheDocument()
})

it.each([
  ['GENERATION_DISABLED', 'Viewer生成は現在無効です。安全性の事前確認が完了していません。'],
  ['CODEX_UNAVAILABLE', 'Codexに接続できません。接続状態を確認してから再試行してください。'],
  ['CODEX_SANDBOX_UNSUPPORTED', 'Codexの安全設定を確認できないため、生成を開始しませんでした。'],
  ['DATABASE_ENCODING_UNSUPPORTED', '保存先DBがUTF8ではないため、生成を開始しませんでした。'],
])('shows %s, trace, preserves input and never retries automatically', async (code, text) => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
    if (init?.method === 'POST') return new Response(JSON.stringify({ code, detail: '安全な説明', trace_id: 'trace-test', retryable: false }), { status: 503 })
    return new Response(JSON.stringify(options), { status: 200 })
  })
  mount('create')
  const user = userEvent.setup()
  await user.type(await screen.findByLabelText('Request'), '入力を保持')
  await user.type(screen.getByLabelText('Additional Instruction'), '補足')
  await user.click(screen.getByRole('button', { name: '生成を開始' }))
  expect(await screen.findByText(text)).toBeInTheDocument()
  expect(screen.getByText(`code: ${code}`)).toBeInTheDocument()
  expect(screen.getByText('trace-test')).toBeInTheDocument()
  expect(screen.getByLabelText('Request')).toHaveValue('入力を保持')
  expect(screen.getByLabelText('Additional Instruction')).toHaveValue('補足')
  await new Promise((resolve) => setTimeout(resolve, 30))
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
})

it('hides retry for a nonretryable Job and shows its trace', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
    id: 'job', status: 'failed', current_phase: 'starting_thread', viewer_id: null,
    error: { code: 'CODEX_SANDBOX_UNSUPPORTED', message: '安全設定確認失敗', retryable: false, trace_id: 'job-trace' },
  }), { status: 200 }))
  mount('job')
  expect(await screen.findByText('job-trace')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: '同じ条件で再試行' })).not.toBeInTheDocument()
})

it('displays a Job retry POST failure without repeating the request', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(async (_url, init) => {
    if (init?.method === 'POST') return new Response(JSON.stringify({ code: 'CODEX_UNAVAILABLE', detail: '接続状態を確認してください。', trace_id: 'retry-trace' }), { status: 503 })
    return new Response(JSON.stringify({ id: 'job', status: 'failed', current_phase: 'analyzing_repository', viewer_id: null, error: { code: 'CODEX_TIMEOUT', message: '時間切れ', retryable: true, trace_id: 'job-trace' } }), { status: 200 })
  })
  mount('job')
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '同じ条件で再試行' }))
  expect(await screen.findByText('retry-trace')).toBeInTheDocument()
  await new Promise((resolve) => setTimeout(resolve, 30))
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(1)
})
