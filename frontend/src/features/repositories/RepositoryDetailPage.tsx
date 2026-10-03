import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '../../lib/api'
import { getRepository, syncRepository } from './repositoryApi'
import { RepositoryStatusBadge } from './RepositoryStatusBadge'
import { isRepositoryProcessing } from './repositoryTypes'

const displayDate = (value: string | null) => value
  ? new Intl.DateTimeFormat('ja-JP', { dateStyle: 'long', timeStyle: 'medium' }).format(new Date(value))
  : 'まだ成功していません'

export function RepositoryDetailPage() {
  const { repositoryId = '' } = useParams()
  const queryClient = useQueryClient()
  const repository = useQuery({
    queryKey: ['repositories', repositoryId],
    queryFn: () => getRepository(repositoryId),
    retry: false,
    refetchInterval: (query) => query.state.data && isRepositoryProcessing(query.state.data) ? 2_000 : false,
  })
  const sync = useMutation({
    mutationFn: () => syncRepository(repositoryId),
    onSuccess: (updated) => {
      queryClient.setQueryData(['repositories', repositoryId], updated)
      void queryClient.invalidateQueries({ queryKey: ['repositories'] })
    },
    onError: (error) => {
      if (error instanceof ApiError && error.problem.code === 'REPOSITORY_BUSY') void repository.refetch()
    },
  })

  if (repository.isPending) return <main className="page-shell"><div className="panel muted">Repositoryを読み込んでいます…</div></main>
  if (repository.isError) {
    const notFound = repository.error instanceof ApiError && repository.error.problem.code === 'REPOSITORY_NOT_FOUND'
    return <main className="page-shell"><div className="error-card" role="alert"><h1>{notFound ? 'Repositoryが見つかりません' : 'Repositoryを取得できませんでした'}</h1>{notFound ? <Link to="/repositories">一覧へ戻る</Link> : <button onClick={() => void repository.refetch()}>再試行</button>}</div></main>
  }
  const item = repository.data
  const processing = isRepositoryProcessing(item)

  return (
    <main className="page-shell">
      <Link className="back-link" to="/repositories">← Repository一覧</Link>
      <div className="page-heading repository-title"><div><span className="eyebrow">REPOSITORY DASHBOARD</span><h1>{item.full_name}</h1><a href={item.github_url} target="_blank" rel="noreferrer">GitHubで開く ↗</a></div><RepositoryStatusBadge status={item.status} /></div>
      <section className="status-panel" aria-live="polite" aria-busy={processing}>
        <div><h2>{processing ? 'Repositoryを準備しています' : item.status === 'failed' ? '処理に失敗しました' : 'Repositoryは利用可能です'}</h2><p className="muted">{processing ? '完了するまでこの画面を自動更新します。' : item.last_error?.message ?? 'Viewer生成の準備ができています。'}</p></div>
        <button className="primary" onClick={() => sync.mutate()} disabled={processing || sync.isPending}>{item.status === 'failed' ? '再試行' : '最新コードを取得'}</button>
      </section>
      {sync.isError && !(sync.error instanceof ApiError && sync.error.problem.code === 'REPOSITORY_BUSY') && <div className="error-card" role="alert"><p>同期を開始できませんでした。もう一度お試しください。</p></div>}
      <section className="detail-grid"><div className="panel"><h2>Repository情報</h2><dl className="detail-list"><div><dt>Default Branch</dt><dd>{item.default_branch ?? '確認中'}</dd></div><div><dt>Commit SHA</dt><dd className="mono break-all">{item.latest_commit_sha ?? '確認中'}</dd></div><div><dt>最終同期日時</dt><dd>{displayDate(item.last_synced_at)}</dd></div><div><dt>登録日時</dt><dd>{displayDate(item.created_at)}</dd></div></dl></div><div className="panel"><div className="panel-heading"><h2>Viewers</h2><button className="secondary" disabled title="Phase 2で利用可能">Viewerを作成</button></div><div className="viewer-placeholder"><p>Viewerはまだありません</p><small>Phase 2で仕様書の生成機能が利用可能になります。</small></div></div></section>
    </main>
  )
}
