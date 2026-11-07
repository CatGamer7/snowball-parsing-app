export interface HealthResponse {
  status: 'ok'
}

export interface ValidateRequest {
  token: string
}

export interface ValidateResponse {
  valid: true
  token_type: 'user' | 'service'
  user?: {
    id: number
    name: string
  }
}

export interface Model {
  id: string
  name: string
  description: string
  task: 'ner'
  settings_schema: Record<string, unknown>
}

export interface Seed {
  type: 'group' | 'user' | 'post'
  id: string
}

export interface GLiNERSettings {
  labels: string[]
}

export type WikiNeuralSettings = Record<string, never>

export type SelectedModels =
  | {
      'urchade/gliner_multi-v2.1': GLiNERSettings
      'Babelscape/wikineural-multilingual-ner'?: WikiNeuralSettings
    }
  | {
      'urchade/gliner_multi-v2.1'?: GLiNERSettings
      'Babelscape/wikineural-multilingual-ner': WikiNeuralSettings
    }

export interface Rules {
  models: SelectedModels
  threshold: number
  max_depth?: number
}

export interface StartRequest {
  token: string
  seeds: Seed[]
  rules: Rules
}

export interface StartResponse {
  collection_id: string
  status: 'running'
}

export type ApiErrorCode =
  | 'INVALID_TOKEN'
  | 'UNSUPPORTED_TOKEN_TYPE'
  | 'MODEL_NOT_FOUND'
  | 'VALIDATION_ERROR'
  | 'VK_QUOTA_EXCEEDED'
  | 'VK_UNAVAILABLE'
  | 'INTERNAL_ERROR'

export interface ErrorResponse {
  error: {
    code: ApiErrorCode
    message: string
  }
}
