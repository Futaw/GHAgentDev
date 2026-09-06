import { useQuery } from '@tanstack/react-query'
import { Navigate, Outlet } from 'react-router-dom'
import { getAuthStatus } from './authApi'

export function RequireAuth() {
  const auth = useQuery({ queryKey: ['auth'], queryFn: getAuthStatus, retry: false })

  if (auth.isPending) return <main className="center-card">認証状態を確認しています…</main>
  if (auth.isError || auth.data.status === 'error') {
    return (
      <main className="center-card">
        <h1>接続を確認できません</h1>
        <p>Codex App Serverとの接続を確認してから再試行してください。</p>
        <button onClick={() => void auth.refetch()}>再試行</button>
      </main>
    )
  }
  if (auth.data.status !== 'authenticated') return <Navigate to="/login" replace />
  return <Outlet />
}
