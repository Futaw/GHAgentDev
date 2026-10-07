import { useEffect, useRef } from 'react'
import { ApiError } from '../../lib/api'

type Props = {
  fullName: string
  isOpen: boolean
  isPending: boolean
  error: Error | null
  onCancel: () => void
  onConfirm: () => void
}

const deleteErrorMessage = (error: Error | null) => {
  if (!(error instanceof ApiError)) return error ? 'Repositoryを削除できませんでした。' : null
  if (error.problem.code === 'REPOSITORY_IN_USE') {
    return '関連するViewerなどを先に削除してください。'
  }
  if (error.problem.code === 'DELETE_FAILED') {
    return '管理Workspaceを削除できませんでした。もう一度お試しください。'
  }
  if (error.problem.code === 'REPOSITORY_BUSY') {
    return 'Cloneまたは同期の完了後に、もう一度お試しください。'
  }
  return error.problem.detail
}

export function RepositoryDeleteDialog({
  fullName,
  isOpen,
  isPending,
  error,
  onCancel,
  onConfirm,
}: Props) {
  const cancelRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    if (isOpen) cancelRef.current?.focus()
  }, [isOpen])

  if (!isOpen) return null
  const errorMessage = deleteErrorMessage(error)

  return (
    <div className="dialog-backdrop">
      <section
        className="delete-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="delete-dialog-title"
        aria-describedby="delete-dialog-description"
        onKeyDown={(event) => {
          if (event.key === 'Escape' && !isPending) onCancel()
        }}
      >
        <span className="eyebrow danger-text">DANGER ZONE</span>
        <h2 id="delete-dialog-title">Repositoryを削除しますか？</h2>
        <p className="delete-target mono">{fullName}</p>
        <p id="delete-dialog-description" className="muted">
          RepoSpec Viewerの登録情報とローカルWorkspaceを削除します。
          GitHub上のRepositoryは削除されません。
        </p>
        {errorMessage && <div className="error-card" role="alert"><p>{errorMessage}</p></div>}
        <div className="dialog-actions">
          <button ref={cancelRef} className="secondary" onClick={onCancel} disabled={isPending}>キャンセル</button>
          <button className="danger" onClick={onConfirm} disabled={isPending}>
            {isPending ? '削除しています…' : '削除する'}
          </button>
        </div>
      </section>
    </div>
  )
}
