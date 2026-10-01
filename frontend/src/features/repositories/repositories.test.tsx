import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { RepositoryListPage } from './RepositoryListPage'
import { RepositoryNewPage } from './RepositoryNewPage'
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

afterEach(() => vi.restoreAllMocks())

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
})
