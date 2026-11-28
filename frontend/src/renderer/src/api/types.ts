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
  | 'COLLECTION_NOT_FOUND'
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

export interface CollectionProgress {
  collection_id: string
  status: 'queued' | 'running' | 'completed' | 'failed'
  started_at: string | null
  finished_at: string | null
  records_count: number
  expansion_level: number
  selected_entities_count: number
  vk_requests_count: number
  error: {
    code: 'ML_NOT_AVAILABLE' | 'ML_ERROR' | 'VK_ERROR' | 'INTERNAL_ERROR'
    message: string
  } | null
  stop_reason:
    'max_depth' | 'no_text_records' | 'no_new_entities' | 'no_new_records' | 'record_limit' | null
}

export interface CollectionRecord {
  source: 'vk'
  kind: 'post'
  id: string
  owner_id: number
  text: string
  date: number
}

export interface CollectionRecords {
  collection_id: string
  total: number
  offset: number
  limit: number
  items: CollectionRecord[]
}
