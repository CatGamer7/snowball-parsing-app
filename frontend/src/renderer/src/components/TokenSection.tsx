import { useState } from 'react'
import { ApiError, validateToken } from '../api'
import { validateTokenInput } from '../validation'

interface TokenSectionProps {
  token: string
  disabled: boolean
  onTokenChange: (value: string) => void
  onVerifiedChange: (verified: boolean) => void
}

export default function TokenSection({
  token,
  disabled,
  onTokenChange,
  onVerifiedChange
}: TokenSectionProps): React.JSX.Element {
  const [visible, setVisible] = useState(false)
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  function changeToken(value: string): void {
    onTokenChange(value)
    onVerifiedChange(false)
    setError('')
    setSuccess('')
  }

  async function checkToken(): Promise<void> {
    const validationError = validateTokenInput(token)

    onVerifiedChange(false)
    setSuccess('')

    if (validationError) {
      setError(validationError)
      return
    }

    setChecking(true)
    setError('')

    try {
      const response = await validateToken({ token })

      setSuccess(
        response.token_type === 'service'
          ? 'Сервисный ключ проверен'
          : 'Пользовательский токен проверен'
      )

      onVerifiedChange(true)
    } catch (caught: unknown) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Не удалось проверить токен. Попробуйте ещё раз'
      )
    } finally {
      setChecking(false)
    }
  }

  const locked = disabled || checking

  return (
    <section className="settings-card" aria-labelledby="token-heading">
      <h2 id="token-heading">1. Доступ к VK API</h2>

      <p className="field-hint">
        Подходит сервисный ключ или пользовательский токен. Тип определяется при проверке.
      </p>

      <label className="field-label" htmlFor="vk-token">
        Токен доступа
      </label>

      <div className="token-row">
        <input
          id="vk-token"
          className={`text-input ${error ? 'input-error' : ''}`}
          type={visible ? 'text' : 'password'}
          value={token}
          disabled={locked}
          autoComplete="off"
          spellCheck={false}
          placeholder="Введите токен VK"
          aria-invalid={Boolean(error)}
          aria-describedby="token-feedback token-privacy"
          onChange={(event) => changeToken(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !locked) {
              event.preventDefault()
              void checkToken()
            }
          }}
        />

        <button
          className="button button-outline"
          type="button"
          disabled={locked}
          aria-label={visible ? 'Скрыть токен' : 'Показать токен'}
          aria-pressed={visible}
          onClick={() => setVisible((previous) => !previous)}
        >
          {visible ? 'Скрыть' : 'Показать'}
        </button>

        <button
          className="button button-outline"
          type="button"
          disabled={locked}
          onClick={() => void checkToken()}
        >
          {checking ? 'Проверяем…' : 'Проверить токен'}
        </button>
      </div>

      <div id="token-feedback" aria-live="polite">
        {error ? (
          <p className="field-error">{error}</p>
        ) : success ? (
          <p className="field-success">{success}</p>
        ) : (
          <p className="field-hint">{checking ? 'Проверка токена…' : 'Статус: не проверен'}</p>
        )}
      </div>

      <div id="token-privacy" className="info-banner">
        Токен используется для запросов к VK API. В интерфейсе он хранится только в памяти и не
        сохраняется после закрытия приложения.
      </div>
    </section>
  )
}
