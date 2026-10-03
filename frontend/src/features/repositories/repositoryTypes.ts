export type RepositoryStatus = 'pending' | 'cloning' | 'ready' | 'syncing' | 'failed'

export type RepositoryError = {
  code: string
  message: string
  retryable: boolean
}

export type Repository = {
  id: string
  owner: string
  name: string
  full_name: string
  github_url: string
  default_branch: string | null
  latest_commit_sha: string | null
  status: RepositoryStatus
  last_synced_at: string | null
  last_error: RepositoryError | null
  viewer_count: number
  created_at: string
  updated_at: string
}

export type RepositoryList = { items: Repository[] }

export const isRepositoryProcessing = (repository: Repository) =>
  repository.status === 'pending' || repository.status === 'cloning' || repository.status === 'syncing'
