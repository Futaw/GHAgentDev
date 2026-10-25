import { api } from '../../lib/api'
import type { GenerationJob, Viewer, ViewerOptions, ViewerSummary } from './viewerTypes'

export type ViewerCreatePayload = {
  request: string
  document_type: string
  detail_level: string
  target_audience: string
  theme_slug: string
  density: string
  additional_instruction: string | null
}

export const getViewerOptions = () => api<ViewerOptions>('/api/viewer-options')
export const listViewers = (repositoryId: string) =>
  api<{ items: ViewerSummary[] }>(`/api/repositories/${repositoryId}/viewers`)
export const getViewer = (viewerId: string) => api<Viewer>(`/api/viewers/${viewerId}`)
export const createViewer = (repositoryId: string, payload: ViewerCreatePayload, key: string) =>
  api<GenerationJob>(`/api/repositories/${repositoryId}/viewers`, {
    method: 'POST',
    headers: { 'Idempotency-Key': key },
    body: JSON.stringify(payload),
  })
export const regenerateViewer = (viewerId: string, key: string) =>
  api<GenerationJob>(`/api/viewers/${viewerId}/regenerate`, {
    method: 'POST',
    headers: { 'Idempotency-Key': key },
  })
export const updateViewerAppearance = (
  viewerId: string,
  payload: { theme_slug?: string; density?: string },
) => api<ViewerSummary>(`/api/viewers/${viewerId}/appearance`, {
  method: 'PATCH', body: JSON.stringify(payload),
})
export const deleteViewer = (viewerId: string) =>
  api<void>(`/api/viewers/${viewerId}`, { method: 'DELETE' })
export const getGenerationJob = (jobId: string) =>
  api<GenerationJob>(`/api/generation-jobs/${jobId}`)
export const cancelGenerationJob = (jobId: string) =>
  api<GenerationJob>(`/api/generation-jobs/${jobId}/cancel`, { method: 'POST' })
export const retryGenerationJob = (jobId: string, key: string) =>
  api<GenerationJob>(`/api/generation-jobs/${jobId}/retry`, {
    method: 'POST', headers: { 'Idempotency-Key': key },
  })
