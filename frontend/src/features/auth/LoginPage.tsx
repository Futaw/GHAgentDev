import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { cancelLogin, getAuthStatus, startLogin } from './authApi'

export function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [loginId, setLoginId] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const auth = useQuery({
    queryKey: ['auth'],
    queryFn: getAuthStatus,
    retry: false,
    refetchInterval: loginId ? 2_000 : false,
  })
  const login = useMutation({
    mutationFn: startLogin,
    onSuccess: (result) => {
      setLoginId(result.login_id)
      setMessage('新しいタブでChatGPTへのログインを完了してください。')
      window.open(result.auth_url, '_blank', 'noopener,noreferrer')
    },
    onError: () => setMessage('ログインを開始できませんでした。接続を確認して再試行してください。'),
  })
  const cancel = useMutation({
    mutationFn: cancelLogin,
    onSuccess: () => {
      setLoginId(null)
      setMessage('ログインをキャンセルしました。')
    },
  })

  useEffect(() => {
    if (!loginId) return
    const stream = new EventSource('/api/auth/events')
    const completed = () => {
      void queryClient.invalidateQueries({ queryKey: ['auth'] })
      navigate('/chat', { replace: true })
    }
    const failed = () => setMessage('ログインを完了できませんでした。もう一度お試しください。')
    stream.addEventListener('auth.authenticated', completed)
    stream.addEventListener('auth.failed', failed)
    return () => stream.close()
  }, [loginId, navigate, queryClient])

  if (auth.data?.status === 'authenticated') return <Navigate to="/chat" replace />
  const disconnected = auth.data?.app_server_connected === false

  return (
    <main className="login-shell">
      <section className="login-card" aria-labelledby="login-title">
        <span className="eyebrow">SOURCE TO SPEC</span>
        <h1 id="login-title">RepoSpec Viewer</h1>
        <p className="lead">ソースコードの背景まで、読み解ける仕様書へ。</p>
        <div className={`status-chip ${disconnected ? 'status-bad' : ''}`} role="status">
          <span aria-hidden="true" />
          {auth.isPending
            ? '認証状態を確認中'
            : disconnected
              ? 'Codex App Server 未接続'
              : 'Codex App Server 接続済み'}
        </div>
        <p className="muted">Codexを利用するにはChatGPTアカウントでの認証が必要です。</p>
        {message && <p className="notice" role="status">{message}</p>}
        {auth.isError || auth.data?.status === 'error' ? (
          <button className="primary" onClick={() => void auth.refetch()}>接続を再確認</button>
        ) : loginId ? (
          <button className="secondary" disabled={cancel.isPending} onClick={() => cancel.mutate(loginId)}>
            ログインをキャンセル
          </button>
        ) : (
          <button className="primary" disabled={login.isPending || disconnected} onClick={() => login.mutate()}>
            {login.isPending ? '開始しています…' : 'ChatGPTでログイン'}
          </button>
        )}
      </section>
    </main>
  )
}
