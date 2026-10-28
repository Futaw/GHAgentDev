export type OptionItem = { value: string; label: string; description: string }
export type ViewerOptions = {
  document_types: OptionItem[]
  detail_levels: OptionItem[]
  target_audiences: OptionItem[]
  themes: OptionItem[]
  densities: OptionItem[]
  defaults: {
    document_type: string
    detail_level: string
    target_audience: string
    theme_slug: string
    density: string
  }
}
export type SourceReference = {
  id: string
  path: string
  start_line: number
  end_line: number
  description: string
}
export type ViewerSummary = {
  id: string
  repository_id: string
  title: string
  summary: string
  document_type: string
  detail_level: string
  target_audience: string
  theme_slug: string
  density: string
  commit_sha: string
  content_revision: number
  created_at: string
  updated_at: string
}
export type Viewer = ViewerSummary & {
  content_json: {
    title: string
    summary: string
    sections: { id: string; heading: string; summary: string | null; blocks: unknown[] }[]
    source_references: SourceReference[]
    limitations: string[]
  }
  sanitized_html: string
  renderer_version: string
  repository: {
    id: string
    full_name: string
    github_url: string
    default_branch: string | null
  }
}
export type GenerationJob = {
  id: string
  repository_id: string
  viewer_id: string | null
  retry_of_job_id: string | null
  operation: 'create' | 'regenerate'
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled'
  current_phase: string
  started_at: string | null
  completed_at: string | null
  error: { code: string; message: string; retryable: boolean } | null
  created_at: string
  updated_at: string
  events_url: string
}
