import { useEffect, useState } from 'react'
import { ApiError, getModels, startCollection } from './api'
import type { Model, Seed, SelectedModels, StartResponse } from './api'
import ModelsSection from './components/ModelsSection'
import type { ModelSettings } from './components/ModelsSection'
import SeedsSection from './components/SeedsSection'
import TokenSection from './components/TokenSection'
import { MAX_SEEDS, validateThreshold, validateTokenInput } from './validation'

const GLINER_ID = 'urchade/gliner_multi-v2.1'
const WIKINEURAL_ID = 'Babelscape/wikineural-multilingual-ner'

function App(): React.JSX.Element {
  const [token, setToken] = useState('')
  const [tokenVerified, setTokenVerified] = useState(false)
  const [seeds, setSeeds] = useState<Seed[]>([])
  const [models, setModels] = useState<Model[]>([])
  const [modelsLoading, setModelsLoading] = useState(true)
  const [modelsError, setModelsError] = useState('')
  const [reloadCount, setReloadCount] = useState(0)
  const [starting, setStarting] = useState(false)
  const [startError, setStartError] = useState('')
  const [started, setStarted] = useState<StartResponse | null>(null)

  const [settings, setSettings] = useState<ModelSettings>({
    gliner: false,
    wikineural: false,
    labels: 'person, organization, city',
    threshold: '0.5',
    maxDepth: 2
  })

  useEffect(() => {
    let active = true

    async function loadModels(): Promise<void> {
      setModelsLoading(true)
      setModelsError('')

      try {
        const catalog = await getModels()

        if (active) {
          setModels(catalog)
        }
      } catch (caught: unknown) {
        if (active) {
          setModels([])
          setModelsError(
            caught instanceof ApiError ? caught.message : 'Не удалось загрузить модели'
          )
        }
      } finally {
        if (active) {
          setModelsLoading(false)
        }
      }
    }

    void loadModels()

    return () => {
      active = false
    }
  }, [reloadCount])

  function clearStartResult(): void {
    setStartError('')
    setStarted(null)
  }

  function changeToken(value: string): void {
    setToken(value)
    setTokenVerified(false)
    clearStartResult()
  }

  function changeSeeds(value: Seed[]): void {
    setSeeds(value)
    clearStartResult()
  }

  function changeSettings(value: ModelSettings): void {
    setSettings(value)
    clearStartResult()
  }

  const labels = Array.from(
    new Set(
      settings.labels
        .split(',')
        .map((label) => label.trim())
        .filter(Boolean)
    )
  )

  const glinerAvailable = models.some((model) => model.id === GLINER_ID)
  const wikineuralAvailable = models.some((model) => model.id === WIKINEURAL_ID)

  let thresholdValid = true

  try {
    validateThreshold(settings.threshold)
  } catch {
    thresholdValid = false
  }

  const selectionValid =
    (settings.gliner || settings.wikineural) &&
    (!settings.gliner || (glinerAvailable && labels.length > 0)) &&
    (!settings.wikineural || wikineuralAvailable)

  const canStart =
    !starting &&
    !modelsLoading &&
    !modelsError &&
    tokenVerified &&
    validateTokenInput(token) === null &&
    seeds.length > 0 &&
    seeds.length <= MAX_SEEDS &&
    selectionValid &&
    thresholdValid &&
    Number.isInteger(settings.maxDepth) &&
    settings.maxDepth >= 1 &&
    settings.maxDepth <= 5

  async function handleStart(): Promise<void> {
    if (!canStart) return

    setStarting(true)
    setStartError('')
    setStarted(null)

    try {
      let selectedModels: SelectedModels

      if (settings.gliner) {
        selectedModels = settings.wikineural
          ? {
              'urchade/gliner_multi-v2.1': { labels },
              'Babelscape/wikineural-multilingual-ner': {}
            }
          : {
              'urchade/gliner_multi-v2.1': { labels }
            }
      } else {
        selectedModels = {
          'Babelscape/wikineural-multilingual-ner': {}
        }
      }

      const response = await startCollection({
        token,
        seeds,
        rules: {
          models: selectedModels,
          threshold: validateThreshold(settings.threshold),
          max_depth: settings.maxDepth
        }
      })

      setStarted(response)
    } catch (caught: unknown) {
      setStartError(
        caught instanceof ApiError
          ? caught.message
          : 'Не удалось отправить задание. Попробуйте ещё раз'
      )
    } finally {
      setStarting(false)
    }
  }

  return (
    <main className="settings-page">
      <h1>Параметры сбора</h1>

      <TokenSection
        token={token}
        disabled={starting}
        onTokenChange={changeToken}
        onVerifiedChange={setTokenVerified}
      />

      <SeedsSection seeds={seeds} disabled={starting} onSeedsChange={changeSeeds} />

      <ModelsSection
        models={models}
        loading={modelsLoading}
        loadError={modelsError}
        disabled={starting}
        settings={settings}
        onSettingsChange={changeSettings}
        onReload={() => {
          setModelsLoading(true)
          setModelsError('')
          clearStartResult()
          setReloadCount((previous) => previous + 1)
        }}
      />

      <div className="start-actions">
        <button
          className="button button-primary"
          type="button"
          disabled={!canStart || started !== null}
          onClick={() => void handleStart()}
        >
          {starting ? 'Отправляем задание…' : started ? 'Задание принято' : 'Начать сбор'}
        </button>

        {!canStart && !starting && !started && (
          <p className="field-hint">
            Проверьте токен, добавьте начальные записи и заполните настройки моделей.
          </p>
        )}
      </div>

      <div aria-live="polite">
        {startError && (
          <div className="error-banner" role="alert">
            {startError}
          </div>
        )}

        {started && (
          <div className="success-banner">
            <strong>Задание принято бэкендом</strong>
            <p>Идентификатор: {started.collection_id}</p>
            <p>
              Фоновый сбор и ML-обработка пока не подключены. Этот ответ подтверждает только
              принятие задания.
            </p>
          </div>
        )}
      </div>
    </main>
  )
}

export default App
