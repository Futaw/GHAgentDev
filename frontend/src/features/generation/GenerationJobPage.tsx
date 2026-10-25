import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { cancelGenerationJob, getGenerationJob, retryGenerationJob } from '../viewers/viewerApi'

const phases = ['preparing_repository', 'starting_thread', 'analyzing_repository', 'validating_document', 'rendering_html', 'sanitizing_html', 'saving_viewer', 'completed']
const labels: Record<string, string> = {
  queued: '実行待ち', preparing_repository: 'Repositoryを確認', starting_thread: '安全な調査環境を開始',
  analyzing_repository: 'Repositoryを調査', validating_document: '文書と参照を検証',
  rendering_html: 'HTMLを生成', sanitizing_html: 'HTMLをサニタイズ', saving_viewer: 'Viewerを保存', completed: '完了',
}

export function GenerationJobPage() {
  const { jobId = '' } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [connection, setConnection] = useState<'connecting' | 'connected' | 'reconnecting'>('connecting')
  const [paths, setPaths] = useState<string[]>([])
  const key = useRef(crypto.randomUUID())
  const job = useQuery({
    queryKey: ['generation-jobs', jobId], queryFn: () => getGenerationJob(jobId), retry: false,
    refetchInterval: (query) => query.state.data && ['queued', 'running'].includes(query.state.data.status) ? 5_000 : false,
  })
  const cancel = useMutation({ mutationFn: () => cancelGenerationJob(jobId), onSuccess: (value) => queryClient.setQueryData(['generation-jobs', jobId], value) })
  const retry = useMutation({ mutationFn: () => retryGenerationJob(jobId, key.current), onSuccess: (value) => navigate(`/jobs/${value.id}`) })
  const jobStatus = job.data?.status
  const eventsUrl = job.data?.events_url

  useEffect(() => {
    if (!jobStatus || !eventsUrl || !['queued', 'running'].includes(jobStatus)) return
    const source = new EventSource(eventsUrl)
    source.onopen = () => setConnection('connected')
    source.onerror = () => setConnection('reconnecting')
    const refresh = () => void queryClient.invalidateQueries({ queryKey: ['generation-jobs', jobId] })
    source.addEventListener('job.phase.changed', refresh)
    source.addEventListener('job.sources.validated', (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { paths?: string[] }
      setPaths(data.paths ?? [])
    })
    source.addEventListener('job.completed', (event) => {
      const data = JSON.parse((event as MessageEvent).data) as { viewer_id: string }
      source.close(); refresh(); navigate(`/viewers/${data.viewer_id}`)
    })
    source.addEventListener('job.failed', () => { source.close(); refresh() })
    source.addEventListener('job.cancelled', () => { source.close(); refresh() })
    return () => source.close()
  }, [jobStatus, eventsUrl, jobId, navigate, queryClient])

  if (job.isPending) return <main className="page-shell"><div className="panel">Jobを読み込んでいます…</div></main>
  if (job.isError) return <main className="page-shell"><div className="error-card">Jobを取得できませんでした。<button onClick={() => void job.refetch()}>再試行</button></div></main>
  const value = job.data
  const index = phases.indexOf(value.current_phase)
  return <main className="page-shell narrow-page">
    <span className="eyebrow">GENERATION JOB</span><h1>Viewerを生成中</h1>
    <section className="panel generation-panel" aria-live="polite" aria-busy={['queued', 'running'].includes(value.status)}>
      <div className={`job-status job-status-${value.status}`}>{value.status}</div>
      {['queued', 'running'].includes(value.status) && <p className="muted">SSE: {connection === 'connected' ? '接続中' : '再接続中'}。RESTでも5秒ごとに状態を確認しています。</p>}
      <ol className="phase-list">{phases.map((phase, phaseIndex) => <li key={phase} className={phaseIndex < index ? 'done' : phaseIndex === index ? 'active' : ''}>{labels[phase]}</li>)}</ol>
      {paths.length > 0 && <div><h2>検証済みソース</h2><ul>{paths.map((path) => <li className="mono" key={path}>{path}</li>)}</ul></div>}
      {value.error && <div className="error-card" role="alert"><strong>{value.error.code}</strong><p>{value.error.message}</p></div>}
      <div className="form-actions">
        {['queued', 'running'].includes(value.status) && <button className="stop" disabled={cancel.isPending} onClick={() => cancel.mutate()}>中止</button>}
        {['failed', 'cancelled'].includes(value.status) && <button className="primary" disabled={retry.isPending || value.error?.retryable === false} onClick={() => retry.mutate()}>同じ条件で再試行</button>}
        {value.viewer_id && <Link className="primary button" to={`/viewers/${value.viewer_id}`}>Viewerを開く</Link>}
      </div>
    </section>
  </main>
}
