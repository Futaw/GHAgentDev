import { Navigate, Route, Routes } from 'react-router-dom'
import { RequireAuth } from '../features/auth/RequireAuth'
import { LoginPage } from '../features/auth/LoginPage'
import { ChatPage } from '../features/chat/ChatPage'
import { RepositoryDetailPage } from '../features/repositories/RepositoryDetailPage'
import { RepositoryListPage } from '../features/repositories/RepositoryListPage'
import { RepositoryNewPage } from '../features/repositories/RepositoryNewPage'
import { AppLayout } from './AppLayout'

export function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="/repositories" element={<RepositoryListPage />} />
          <Route path="/repositories/new" element={<RepositoryNewPage />} />
          <Route path="/repositories/:repositoryId" element={<RepositoryDetailPage />} />
          <Route path="/chat" element={<ChatPage />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/repositories" replace />} />
    </Routes>
  )
}
