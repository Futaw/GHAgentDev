import { useQuery } from '@tanstack/react-query'
import { NavLink, Outlet } from 'react-router-dom'
import { api } from '../lib/api'
import type { Health } from '../lib/types'

export function AppLayout() {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api<Health>('/api/health'),
    refetchInterval: 5_000,
  })

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand"><span className="mark">R</span><strong>RepoSpec Viewer</strong></div>
        <nav aria-label="メインナビゲーション">
          <NavLink to="/repositories">Repositories</NavLink>
          <NavLink to="/chat">Chat</NavLink>
        </nav>
        <div className={`connection ${health.data?.app_server_connected ? '' : 'offline'}`} role="status">
          <span /> {health.data?.app_server_connected ? 'App Server 接続済み' : 'App Server 未接続'}
        </div>
      </header>
      <Outlet />
    </div>
  )
}
