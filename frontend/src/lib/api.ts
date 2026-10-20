export type ProblemDetails = {
  title: string
  detail: string
  status: number
  code: string
  retryable: boolean
  trace_id: string
  repository_id?: string
}
export class ApiError extends Error {
  constructor(readonly problem: ProblemDetails) {
    super(problem.detail)
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      ...init,
      headers: {
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
    })
  } catch {
    throw new ApiError({
      title: 'Network error',
      detail: 'サーバーへ接続できません。接続状態を確認して再試行してください。',
      status: 0,
      code: 'NETWORK_ERROR',
      retryable: true,
      trace_id: '',
    })
  }
  if (!response.ok) {
    let problem: ProblemDetails
    try {
      problem = (await response.json()) as ProblemDetails
    } catch {
      problem = {
        title: 'Request failed',
        detail: 'サーバーへのリクエストに失敗しました。',
        status: response.status,
        code: 'HTTP_ERROR',
        retryable: response.status >= 500,
        trace_id: '',
      }
    }
    throw new ApiError(problem)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}
