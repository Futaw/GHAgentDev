import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { listRepositories } from './repositoryApi'
import { RepositoryStatusBadge } from './RepositoryStatusBadge'
import { isRepositoryProcessing } from './repositoryTypes'

const dateTime = (value: string | null) => value
  ? new Intl.DateTimeFormat('ja-JP', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value))
  : '未同期'

export function RepositoryListPage() {
  const repositories = useQuery({
    queryKey: ['repositories'],
    queryFn: listRepositories,
    refetchInterval: (query) => query.state.data?.items.some(isRepositoryProcessing) ? 2_000 : false,
  })

  return (
    <main className="page-shell">
      <div className="page-heading">
        <div><span className="eyebrow">MANAGED WORKSPACES</span><h1>Repositories</h1><p>調査対象のPublic GitHub Repositoryを管理します。</p></div>
        <Link className="button primary" to="/repositories/new">Repositoryを登録</Link>
      </div>
      {repositories.isPending && <div className="panel muted">Repositoryを読み込んでいます…</div>}
      {repositories.isError && (
        <div className="error-card" role="alert"><p>Repository一覧を取得できませんでした。</p><button onClick={() => void repositories.refetch()}>再試行</button></div>
      )}
      {repositories.data?.items.length === 0 && (
        <section className="empty-state"><h2>Repositoryはまだありません</h2><p>Public GitHub Repositoryを登録すると、Clone状態とCommitをここで確認できます。</p><Link className="button primary" to="/repositories/new">最初のRepositoryを登録</Link></section>
      )}
      {!!repositories.data?.items.length && (
        <section className="repository-grid" aria-live="polite">
          {repositories.data.items.map((repository) => (
            <article className="repository-card" key={repository.id}>
              <div className="repository-card-heading"><div><h2>{repository.full_name}</h2><a href={repository.github_url} target="_blank" rel="noreferrer">{repository.github_url}</a></div><RepositoryStatusBadge status={repository.status} /></div>
              <dl className="metadata-grid"><div><dt>Default Branch</dt><dd>{repository.default_branch ?? '確認中'}</dd></div><div><dt>Commit</dt><dd title={repository.latest_commit_sha ?? undefined} className="mono">{repository.latest_commit_sha?.slice(0, 7) ?? '—'}</dd></div><div><dt>最終同期</dt><dd>{dateTime(repository.last_synced_at)}</dd></div><div><dt>Viewers</dt><dd>{repository.viewer_count}</dd></div></dl>
              {repository.last_error && <p className="inline-error">{repository.last_error.message}</p>}
              <Link className="text-link" to={`/repositories/${repository.id}`}>Dashboardを開く →</Link>
            </article>
          ))}
        </section>
      )}
    </main>
  )
}
