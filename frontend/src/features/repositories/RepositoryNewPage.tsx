import { useMutation, useQueryClient } from '@tanstack/react-query'
import { FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../../lib/api'
import { createRepository } from './repositoryApi'

const githubPattern = /^https:\/\/github\.com\/[A-Za-z0-9-]{1,39}\/[A-Za-z0-9._-]{1,100}(?:\.git)?\/?$/

export function RepositoryNewPage() {
  const [githubUrl, setGithubUrl] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const create = useMutation({
    mutationFn: createRepository,
    onSuccess: (repository) => {
      queryClient.setQueryData(['repositories', repository.id], repository)
      void queryClient.invalidateQueries({ queryKey: ['repositories'] })
      navigate(`/repositories/${repository.id}`)
    },
  })

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const value = githubUrl.trim()
    if (!value) return setValidationError('GitHub URLを入力してください。')
    if (value.length > 2048 || !githubPattern.test(value)) {
      return setValidationError('https://github.com/owner/repository 形式で入力してください。')
    }
    setValidationError(null)
    create.mutate(value)
  }
  const problem = create.error instanceof ApiError ? create.error.problem : null

  return (
    <main className="page-shell narrow-page">
      <Link className="back-link" to="/repositories">← Repository一覧</Link>
      <section className="form-panel"><span className="eyebrow">NEW REPOSITORY</span><h1>Repositoryを登録</h1><p className="muted">Public GitHub Repositoryだけを登録できます。認証情報は使用しません。</p>
        <form onSubmit={submit} noValidate>
          <label htmlFor="github-url">GitHub URL</label>
          <input id="github-url" type="url" value={githubUrl} onChange={(event) => setGithubUrl(event.target.value)} placeholder="https://github.com/owner/repository" maxLength={2048} disabled={create.isPending} aria-describedby="github-url-help github-url-error" />
          <small id="github-url-help">HTTPS URLを入力してください。.git付きも利用できます。</small>
          {(validationError || problem?.code === 'INVALID_GITHUB_URL') && <p id="github-url-error" className="field-error" role="alert">{validationError ?? problem?.detail}</p>}
          {problem?.code === 'REPOSITORY_ALREADY_REGISTERED' && <div className="notice" role="alert">このRepositoryは登録済みです。{problem.repository_id && <Link to={`/repositories/${problem.repository_id}`}>既存のRepositoryを開く</Link>}</div>}
          {create.isError && !['INVALID_GITHUB_URL', 'REPOSITORY_ALREADY_REGISTERED'].includes(problem?.code ?? '') && <div className="error-card" role="alert"><p>{problem?.detail ?? 'Repositoryを登録できませんでした。'}</p></div>}
          <div className="form-actions"><Link className="button secondary" to="/repositories">キャンセル</Link><button className="primary" type="submit" disabled={create.isPending}>{create.isPending ? '登録しています…' : '登録してCloneを開始'}</button></div>
        </form>
      </section>
    </main>
  )
}
