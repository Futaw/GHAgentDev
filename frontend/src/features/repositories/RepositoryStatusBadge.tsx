import type { RepositoryStatus } from './repositoryTypes'

const labels: Record<RepositoryStatus, string> = {
  pending: '待機中',
  cloning: 'Clone中',
  ready: '準備完了',
  syncing: '同期中',
  failed: '失敗',
}

export function RepositoryStatusBadge({ status }: { status: RepositoryStatus }) {
  return <span className={`repository-status status-${status}`}><span aria-hidden="true" />{labels[status]}</span>
}
