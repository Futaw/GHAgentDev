type Props = { isOpen: boolean; pending: boolean; title: string; onCancel: () => void; onConfirm: () => void }
export function ViewerDeleteDialog(props: Props) {
  if (!props.isOpen) return null
  return <div className="dialog-backdrop" role="presentation"><div className="delete-dialog" role="dialog" aria-modal="true" aria-labelledby="viewer-delete-title">
    <span className="eyebrow danger-text">DELETE VIEWER</span><h2 id="viewer-delete-title">Viewerを削除しますか？</h2><p>「{props.title}」と生成元Commitを保持する管理refを削除します。RepositoryとGitHub上のデータは変更しません。</p>
    <div className="dialog-actions"><button className="secondary" disabled={props.pending} onClick={props.onCancel}>キャンセル</button><button className="danger" disabled={props.pending} onClick={props.onConfirm}>Viewerを削除</button></div>
  </div></div>
}
