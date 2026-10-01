import { api } from '../../lib/api'
import type { Repository, RepositoryList } from './repositoryTypes'

export const listRepositories = () => api<RepositoryList>('/api/repositories')

export const getRepository = (repositoryId: string) =>
  api<Repository>(`/api/repositories/${encodeURIComponent(repositoryId)}`)

export const createRepository = (githubUrl: string) =>
  api<Repository>('/api/repositories', {
    method: 'POST',
    body: JSON.stringify({ github_url: githubUrl }),
  })

export const syncRepository = (repositoryId: string) =>
  api<Repository>(`/api/repositories/${encodeURIComponent(repositoryId)}/sync`, { method: 'POST' })
