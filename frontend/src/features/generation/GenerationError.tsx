import { ApiError } from '../../lib/api'

const messages: Record<string, string> = {
  GENERATION_DISABLED: 'Viewer生成は現在無効です。安全性の事前確認が完了していません。',
  CODEX_UNAVAILABLE: 'Codexに接続できません。接続状態を確認してから再試行してください。',
  CODEX_SANDBOX_UNSUPPORTED: 'Codexの安全設定を確認できないため、生成を開始しませんでした。',
}

type Failure = { code: string; message: string; trace_id?: string }
export function GenerationError({ error, failure }: { error?: unknown; failure?: Failure }) {
  const problem = error instanceof ApiError ? error.problem : undefined
  const code = problem?.code ?? failure?.code ?? 'NETWORK_ERROR'
  const detail = problem?.detail ?? failure?.message ?? 'サーバーとの通信に失敗しました。接続状態を確認して再試行してください。'
  const trace = problem?.trace_id ?? failure?.trace_id
  return <div className="error-card" role="alert">
    <strong>{messages[code] ?? 'Viewer生成の処理に失敗しました。'}</strong>
    <p>{detail}</p><p>code: {code}</p>
    {trace && <p>trace ID: <code>{trace}</code></p>}
  </div>
}
