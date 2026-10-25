import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { MouseEvent, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { deleteViewer, getViewer, regenerateViewer, updateViewerAppearance } from './viewerApi'
import { ViewerAppearanceDialog } from './ViewerAppearanceDialog'
import { ViewerDeleteDialog } from './ViewerDeleteDialog'
import { sanitizeViewerHtml } from './viewerSanitizer'
import type { SourceReference } from './viewerTypes'

export function ViewerPage() {
  const { viewerId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [appearanceOpen, setAppearanceOpen] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [source, setSource] = useState<SourceReference | null>(null)
  const viewer = useQuery({ queryKey: ['viewers', viewerId], queryFn: () => getViewer(viewerId), retry: false })
  const regenerate = useMutation({ mutationFn: () => regenerateViewer(viewerId, crypto.randomUUID()), onSuccess: (job) => navigate(`/jobs/${job.id}`) })
  const appearance = useMutation({ mutationFn: (value: { theme_slug: string; density: string }) => updateViewerAppearance(viewerId, value), onSuccess: () => { setAppearanceOpen(false); void queryClient.invalidateQueries({ queryKey: ['viewers', viewerId] }) } })
  const remove = useMutation({ mutationFn: () => deleteViewer(viewerId), onSuccess: () => { if (viewer.data) navigate(`/repositories/${viewer.data.repository_id}`) } })
  const html = useMemo(() => sanitizeViewerHtml(viewer.data?.sanitized_html ?? ''), [viewer.data?.sanitized_html])
  if (viewer.isPending) return <main className="page-shell"><div className="panel">Viewerを読み込んでいます…</div></main>
  if (viewer.isError) return <main className="page-shell"><div className="error-card">Viewerを取得できませんでした。<button onClick={() => void viewer.refetch()}>再試行</button></div></main>
  const value = viewer.data
  const onDocumentClick = (event: MouseEvent<HTMLDivElement>) => {
    const target = (event.target as HTMLElement).closest<HTMLElement>('[data-source-reference-id]')
    if (!target) return
    const found = value.content_json.source_references.find((item) => item.id === target.dataset.sourceReferenceId)
    if (found) setSource(found)
  }
  const commitUrl = `${value.repository.github_url}/tree/${value.commit_sha}`
  return <main className={`viewer-page viewer-theme-${value.theme_slug} viewer-density-${value.density}`}>
    <header className="viewer-header"><div><Link to={`/repositories/${value.repository_id}`}>← {value.repository.full_name}</Link><h1>{value.title}</h1><p>{value.summary}</p></div>
      <div className="viewer-actions"><button className="secondary" onClick={() => setAppearanceOpen(true)}>表示設定</button><button className="secondary" disabled={regenerate.isPending} onClick={() => regenerate.mutate()}>再生成</button><button className="danger-outline" onClick={() => setDeleteOpen(true)}>削除</button></div>
      <dl className="viewer-metadata"><div><dt>Branch</dt><dd>{value.repository.default_branch ?? '—'}</dd></div><div><dt>Commit</dt><dd><a className="mono" href={commitUrl} target="_blank" rel="noopener noreferrer">{value.commit_sha.slice(0, 12)} ↗</a></dd></div><div><dt>Type / Detail</dt><dd>{value.document_type} / {value.detail_level}</dd></div><div><dt>Audience</dt><dd>{value.target_audience}</dd></div><div><dt>Theme / Density</dt><dd>{value.theme_slug} / {value.density}</dd></div><div><dt>Updated</dt><dd>{new Date(value.updated_at).toLocaleString()}</dd></div></dl>
    </header>
    <div className="viewer-shell"><details className="viewer-toc" open><summary>目次</summary><nav aria-label="目次"><ol>{value.content_json.sections.map((section) => <li key={section.id}><a href={`#${section.id}`}>{section.heading}</a></li>)}</ol></nav></details>
      <div className="viewer-document-container" onClick={onDocumentClick} dangerouslySetInnerHTML={{ __html: html }} />
    </div>
    {source && <div className="source-popover" role="dialog" aria-modal="true" aria-labelledby="source-title"><div><h2 id="source-title">{source.description}</h2><p className="mono">{source.path}:{source.start_line}–{source.end_line}</p><p>Source Code ViewerはPhase 3で追加します。</p><button className="secondary" onClick={() => setSource(null)}>閉じる</button></div></div>}
    <ViewerAppearanceDialog isOpen={appearanceOpen} theme={value.theme_slug} density={value.density} pending={appearance.isPending} onClose={() => setAppearanceOpen(false)} onSave={(theme_slug, density) => appearance.mutate({ theme_slug, density })} />
    <ViewerDeleteDialog isOpen={deleteOpen} pending={remove.isPending} title={value.title} onCancel={() => setDeleteOpen(false)} onConfirm={() => remove.mutate()} />
  </main>
}
