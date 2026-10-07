import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RepositoryListPage } from './RepositoryListPage'
import { RepositoryNewPage } from './RepositoryNewPage'
import { RepositoryDetailPage } from './RepositoryDetailPage'
import { isRepositoryProcessing, type Repository } from './repositoryTypes'

const repository = (status: Repository['status']): Repository => ({
  id: '8d66ac14-9530-4777-a643-2513bd1c9a38',
  owner: 'Futaw',
  name: 'GHAgentDev',
  full_name: 'Futaw/GHAgentDev',
  github_url: 'https://github.com/futaw/ghagentdev',
  default_branch: status === 'ready' ? 'main' : null,
  latest_commit_sha: status === 'ready' ? '62e9167c00000000000000000000000000000000' : null,
  status,
  last_synced_at: status === 'ready' ? '2026-09-30T03:00:00Z' : null,
  last_error: status === 'failed' ? { code: 'CLONE_FAILED', message: 'Cloneできませんでした。', retryable: true } : null,
  viewer_count: 0,
  created_at: '2026-09-30T02:59:50Z',
  updated_at: '2026-09-30T03:00:00Z',
})

function renderWithClient(element: React.ReactNode, initialPath = '/') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={[initialPath]}>{element}</MemoryRouter></QueryClientProvider>)
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe('Repository pages', () => {
  it('shows an empty state when no repositories are registered', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ items: [] }), { status: 200 }))
    renderWithClient(<RepositoryListPage />)
    expect(await screen.findByText('Repositoryはまだありません')).toBeInTheDocument()
  })

  it('renders ready, processing, and failed states', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ items: [repository('ready'), { ...repository('cloning'), id: '2' }, { ...repository('failed'), id: '3' }] }), { status: 200 }))
    renderWithClient(<RepositoryListPage />)
    expect(await screen.findByText('準備完了')).toBeInTheDocument()
    expect(screen.getByText('Clone中')).toBeInTheDocument()
    expect(screen.getByText('失敗')).toBeInTheDocument()
    expect(screen.getByText('Cloneできませんでした。')).toBeInTheDocument()
  })

  it('validates the URL and navigates after successful registration', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(repository('pending')), { status: 202 }))
    renderWithClient(<Routes><Route path="/repositories/new" element={<RepositoryNewPage />} /><Route path="/repositories/:repositoryId" element={<p>Dashboard</p>} /></Routes>, '/repositories/new')

    await user.click(screen.getByRole('button', { name: '登録してCloneを開始' }))
    expect(screen.getByText('GitHub URLを入力してください。')).toBeInTheDocument()
    await user.type(screen.getByLabelText('GitHub URL'), 'https://example.com/owner/repo')
    await user.click(screen.getByRole('button', { name: '登録してCloneを開始' }))
    expect(screen.getByText(/https:\/\/github.com\/owner\/repository/)).toBeInTheDocument()
    await user.clear(screen.getByLabelText('GitHub URL'))
    await user.type(screen.getByLabelText('GitHub URL'), 'https://github.com/Futaw/GHAgentDev')
    await user.click(screen.getByRole('button', { name: '登録してCloneを開始' }))
    await waitFor(() => expect(screen.getByText('Dashboard')).toBeInTheDocument())
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('identifies only active states as processing', () => {
    expect(isRepositoryProcessing(repository('pending'))).toBe(true)
    expect(isRepositoryProcessing(repository('cloning'))).toBe(true)
    expect(isRepositoryProcessing(repository('syncing'))).toBe(true)
    expect(isRepositoryProcessing(repository('ready'))).toBe(false)
    expect(isRepositoryProcessing(repository('failed'))).toBe(false)
  })

  it('confirms deletion and returns to the repository list', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(repository('ready')), { status: 200 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }))

    renderWithClient(
      <Routes>
        <Route path="/repositories/:repositoryId" element={<RepositoryDetailPage />} />
        <Route path="/repositories" element={<p>Repository list</p>} />
      </Routes>,
      `/repositories/${repository('ready').id}`,
    )

    expect(await screen.findByRole('heading', { name: 'Futaw/GHAgentDev' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Repositoryを削除' }))
    const cancel = screen.getByRole('button', { name: 'キャンセル' })
    expect(cancel).toHaveFocus()
    expect(screen.getByText(/GitHub上のRepositoryは削除されません。/)).toBeInTheDocument()
    await user.click(cancel)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Repositoryを削除' }))
    await user.click(screen.getByRole('button', { name: '削除する' }))
    expect(await screen.findByText('Repository list')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      `/api/repositories/${repository('ready').id}`,
      expect.objectContaining({ method: 'DELETE' }),
    )
  })

  it('keeps the confirmation dialog open when deletion fails', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(repository('ready')), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({
        title: 'Repository deletion failed',
        detail: '管理Workspaceを削除できませんでした。再試行してください。',
        status: 500,
        code: 'DELETE_FAILED',
        retryable: true,
        trace_id: 'delete-failed',
      }), { status: 500, headers: { 'Content-Type': 'application/problem+json' } }))

    renderWithClient(
      <Routes><Route path="/repositories/:repositoryId" element={<RepositoryDetailPage />} /></Routes>,
      `/repositories/${repository('ready').id}`,
    )

    await screen.findByRole('heading', { name: 'Futaw/GHAgentDev' })
    await user.click(screen.getByRole('button', { name: 'Repositoryを削除' }))
    await user.click(screen.getByRole('button', { name: '削除する' }))
    expect(await screen.findByText('管理Workspaceを削除できませんでした。もう一度お試しください。')).toBeInTheDocument()
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('disables deletion while related viewers exist', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({
      ...repository('ready'),
      viewer_count: 1,
    }), { status: 200 }))

    renderWithClient(
      <Routes><Route path="/repositories/:repositoryId" element={<RepositoryDetailPage />} /></Routes>,
      `/repositories/${repository('ready').id}`,
    )

    expect(await screen.findByRole('button', { name: 'Repositoryを削除' })).toBeDisabled()
    expect(screen.getByText('関連するViewerを先に削除してください。')).toBeInTheDocument()
  })
})
