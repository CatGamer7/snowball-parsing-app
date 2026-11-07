import { API_BASE_URL, API_TIMEOUT_MS } from './config'
import { ApiError } from './errors'
import type {
  ApiErrorCode,
  HealthResponse,
  Model,
  StartRequest,
  StartResponse,
  ValidateRequest,
  ValidateResponse
} from './types'

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isNonBlank(value: unknown): value is string {
  return typeof value === 'string' && value.trim().length > 0
}

const ERROR_CODES: ApiErrorCode[] = [
  'INVALID_TOKEN',
  'UNSUPPORTED_TOKEN_TYPE',
  'MODEL_NOT_FOUND',
  'VALIDATION_ERROR',
  'VK_QUOTA_EXCEEDED',
  'VK_UNAVAILABLE',
  'INTERNAL_ERROR'
]

function isErrorCode(value: unknown): value is ApiErrorCode {
  return ERROR_CODES.some((code) => code === value)
}

function isHealthResponse(value: unknown): value is HealthResponse {
  return isObject(value) && value.status === 'ok'
}

function isValidateResponse(value: unknown): value is ValidateResponse {
  if (!isObject(value)) return false

  if (value.valid !== true || (value.token_type !== 'user' && value.token_type !== 'service')) {
    return false
  }

  if (value.user === undefined) return true

  return (
    isObject(value.user) && Number.isInteger(value.user.id) && typeof value.user.name === 'string'
  )
}

function isModel(value: unknown): value is Model {
  return (
    isObject(value) &&
    isNonBlank(value.id) &&
    isNonBlank(value.name) &&
    typeof value.description === 'string' &&
    value.task === 'ner' &&
    isObject(value.settings_schema)
  )
}

function isModelsResponse(value: unknown): value is Model[] {
  return Array.isArray(value) && value.every(isModel)
}

function isStartResponse(value: unknown): value is StartResponse {
  return isObject(value) && isNonBlank(value.collection_id) && value.status === 'running'
}

async function request<T>(
  path: string,
  method: 'GET' | 'POST',
  expectedStatus: number,
  isValid: (value: unknown) => value is T,
  body?: unknown
): Promise<T> {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), API_TIMEOUT_MS)

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      signal: controller.signal,
      credentials: 'omit',
      cache: 'no-store',
      headers:
        body === undefined
          ? { Accept: 'application/json' }
          : {
              Accept: 'application/json',
              'Content-Type': 'application/json'
            },
      body: body === undefined ? undefined : JSON.stringify(body)
    })

    const text = await response.text()
    let data: unknown

    try {
      data = JSON.parse(text)
    } catch {
      if (!response.ok) {
        throw new ApiError('http', `Сервер вернул ошибку HTTP ${response.status}`, response.status)
      }

      throw new ApiError(
        'invalid_response',
        'Сервер вернул ответ не в формате JSON',
        response.status
      )
    }

    if (!response.ok) {
      let message = `Сервер вернул ошибку HTTP ${response.status}`
      let code: ApiErrorCode | undefined

      if (isObject(data) && isObject(data.error)) {
        if (isNonBlank(data.error.message)) {
          message = data.error.message
        }

        if (isErrorCode(data.error.code)) {
          code = data.error.code
        }
      }

      throw new ApiError('http', message, response.status, code)
    }

    if (response.status !== expectedStatus || !isValid(data)) {
      throw new ApiError(
        'invalid_response',
        'Ответ сервера не соответствует API-контракту',
        response.status
      )
    }

    return data
  } catch (error: unknown) {
    if (error instanceof ApiError) {
      throw error
    }

    if (controller.signal.aborted) {
      throw new ApiError('timeout', 'Сервер не ответил вовремя. Попробуйте ещё раз')
    }

    throw new ApiError('network', 'Не удалось подключиться к серверу. Проверьте, запущен ли бэкенд')
  } finally {
    clearTimeout(timeout)
  }
}

export function checkHealth(): Promise<HealthResponse> {
  return request('/health', 'GET', 200, isHealthResponse)
}

export function validateToken(data: ValidateRequest): Promise<ValidateResponse> {
  return request('/vk/validate', 'POST', 200, isValidateResponse, data)
}

export function getModels(): Promise<Model[]> {
  return request('/collection/models', 'GET', 200, isModelsResponse)
}

export function startCollection(data: StartRequest): Promise<StartResponse> {
  return request('/collection/start', 'POST', 202, isStartResponse, data)
}
