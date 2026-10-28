import { zodResolver } from '@hookform/resolvers/zod'
import { useMutation, useQuery } from '@tanstack/react-query'
import { useRef } from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { z } from 'zod'
import { createViewer, getViewerOptions } from './viewerApi'

const schema = z.object({
  request: z.string().trim().min(1, '生成対象を入力してください。').max(4000),
  document_type: z.string(),
  detail_level: z.string(),
  target_audience: z.string(),
  theme_slug: z.string(),
  density: z.string(),
  additional_instruction: z.string().max(4000),
})
type FormValues = z.infer<typeof schema>

export function ViewerCreatePage() {
  const { repositoryId = '' } = useParams()
  const navigate = useNavigate()
  const key = useRef(crypto.randomUUID())
  const options = useQuery({ queryKey: ['viewer-options'], queryFn: getViewerOptions })
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      request: '', document_type: 'functional_spec', detail_level: 'standard',
      target_audience: 'engineer', theme_slug: 'technical-light', density: 'comfortable',
      additional_instruction: '',
    },
  })
  const create = useMutation({
    mutationFn: (values: FormValues) => createViewer(repositoryId, {
      ...values,
      additional_instruction: values.additional_instruction.trim() || null,
    }, key.current),
    onSuccess: (job) => navigate(`/jobs/${job.id}`),
  })
  const theme = form.watch('theme_slug')
  const density = form.watch('density')

  if (options.isPending) return <main className="page-shell"><div className="panel">選択肢を読み込んでいます…</div></main>
  if (options.isError) return <main className="page-shell"><div className="error-card">選択肢を取得できませんでした。<button onClick={() => void options.refetch()}>再試行</button></div></main>
  const selects: [keyof FormValues, string, typeof options.data.document_types][] = [
    ['document_type', 'Document Type', options.data.document_types],
    ['detail_level', 'Detail Level', options.data.detail_levels],
    ['target_audience', 'Target Audience', options.data.target_audiences],
    ['theme_slug', 'Theme', options.data.themes],
    ['density', 'Density', options.data.densities],
  ]
  return <main className="page-shell narrow-page">
    <Link className="back-link" to={`/repositories/${repositoryId}`}>← Repository Dashboard</Link>
    <section className="form-panel"><span className="eyebrow">NEW VIEWER</span><h1>Viewerを作成</h1>
      <form onSubmit={form.handleSubmit((values) => create.mutate(values))}>
        <label htmlFor="request">Request</label>
        <textarea id="request" rows={6} disabled={create.isPending} {...form.register('request')} />
        {form.formState.errors.request && <p className="field-error">{form.formState.errors.request.message}</p>}
        <div className="viewer-form-grid">{selects.map(([name, label, items]) => <div key={name}>
          <label htmlFor={name}>{label}</label><select id={name} disabled={create.isPending} {...form.register(name)}>
            {items.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </div>)}</div>
        <div className={`viewer-preview viewer-theme-${theme} viewer-density-${density}`}>
          <span>PREVIEW</span><h2>安全な構造化Viewer</h2><p>ThemeとDensityだけを確認する固定sampleです。章構成は生成内容に応じて変わります。</p>
        </div>
        <label htmlFor="additional_instruction">Additional Instruction</label>
        <textarea id="additional_instruction" rows={4} disabled={create.isPending} {...form.register('additional_instruction')} />
        {create.isError && <div className="error-card" role="alert">Viewer生成を開始できませんでした。</div>}
        <div className="form-actions"><Link className="secondary button" to={`/repositories/${repositoryId}`}>戻る</Link><button className="primary" disabled={create.isPending}>生成を開始</button></div>
      </form>
    </section>
  </main>
}
