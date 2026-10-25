import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ViewerPage } from './ViewerPage'
import { sanitizeViewerHtml } from './viewerSanitizer'
import type { Viewer } from './viewerTypes'

const viewer: Viewer = {
  id: 'viewer-id', repository_id: 'repository-id', title: 'Viewer title', summary: 'Summary',
  document_type: 'functional_spec', detail_level: 'standard', target_audience: 'engineer',
  theme_slug: 'technical-light', density: 'comfortable', commit_sha: 'a'.repeat(40),
  content_revision: 1, created_at: '2026-10-25T00:00:00Z', updated_at: '2026-10-25T00:00:00Z',
  content_json: {
    title: 'Viewer title', summary: 'Summary', limitations: [],
    sections: [{ id: 'overview', heading: 'Overview', summary: null, blocks: [] }],
    source_references: [{ id: 'source-main', path: 'src/main.ts', start_line: 2, end_line: 4, description: 'Main source' }],
  },
  sanitized_html: '<article class="viewer-document"><section id="overview"><h2>Overview</h2><button type="button" data-source-reference-id="source-main">Main source</button><script>window.pwned=true</script></section></article>',
  renderer_version: 'viewer-html-v1',
  repository: { id: 'repository-id', full_name: 'example/repo', github_url: 'https://github.com/example/repo', default_branch: 'main' },
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}><MemoryRouter initialEntries={['/viewers/viewer-id']}><Routes><Route path="/viewers/:viewerId" element={<ViewerPage />} /></Routes></MemoryRouter></QueryClientProvider>)
}

afterEach(() => { cleanup(); vi.restoreAllMocks() })

describe('Viewer', () => {
  it('removes active content in the browser sanitizer', () => {
    const result = sanitizeViewerHtml('<img src=x onerror=alert(1)><script>alert(1)</script><p onclick="x">safe</p>')
    expect(result).toBe('<p>safe</p>')
  })

  it('renders sanitized HTML and resolves source clicks from structured data', async () => {
    const user = userEvent.setup()
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify(viewer), { status: 200 }))
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Viewer title' })).toBeInTheDocument()
    expect(document.querySelector('script')).toBeNull()
    await user.click(screen.getByRole('button', { name: 'Main source' }))
    expect(screen.getByText('src/main.ts:2–4')).toBeInTheDocument()
    expect(screen.getByText('Source Code ViewerはPhase 3で追加します。')).toBeInTheDocument()
  })

  it('changes appearance without regenerating', async () => {
    const user = userEvent.setup()
    const fetchMock = vi.spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(viewer), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...viewer, theme_slug: 'editorial', density: 'compact' }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...viewer, theme_slug: 'editorial', density: 'compact' }), { status: 200 }))
    renderPage()
    await screen.findByRole('heading', { name: 'Viewer title' })
    await user.click(screen.getByRole('button', { name: '表示設定' }))
    await user.selectOptions(screen.getByLabelText('Theme'), 'editorial')
    await user.selectOptions(screen.getByLabelText('Density'), 'compact')
    await user.click(screen.getByRole('button', { name: '保存' }))
    expect(fetchMock).toHaveBeenCalledWith('/api/viewers/viewer-id/appearance', expect.objectContaining({ method: 'PATCH' }))
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('regenerate'))).toBe(false)
  })
})
