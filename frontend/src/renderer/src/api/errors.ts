import type { ApiErrorCode } from './types'

export type ApiErrorKind = 'network' | 'timeout' | 'http' | 'invalid_response'

export class ApiError extends Error {
  readonly kind: ApiErrorKind
  readonly status?: number
  readonly code?: ApiErrorCode

  constructor(kind: ApiErrorKind, message: string, status?: number, code?: ApiErrorCode) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
    this.code = code
  }
}
