import type { Model } from '../api'
import { validateThreshold } from '../validation'

export interface ModelSettings {
  gliner: boolean
  wikineural: boolean
  labels: string
  threshold: string
  maxDepth: number
}

interface ModelsSectionProps {
  models: Model[]
  loading: boolean
  loadError: string
  disabled: boolean
  settings: ModelSettings
  onSettingsChange: (settings: ModelSettings) => void
  onReload: () => void
}

const GLINER_ID = 'urchade/gliner_multi-v2.1'
const WIKINEURAL_ID = 'Babelscape/wikineural-multilingual-ner'

export default function ModelsSection({
  models,
  loading,
  loadError,
  disabled,
  settings,
  onSettingsChange,
  onReload
}: ModelsSectionProps): React.JSX.Element {
  const gliner = models.find((model) => model.id === GLINER_ID)
  const wikineural = models.find((model) => model.id === WIKINEURAL_ID)
  const locked = disabled || loading || Boolean(loadError)

  let thresholdError = ''
  let sliderValue = 0.5

  try {
    sliderValue = validateThreshold(settings.threshold)
  } catch (caught: unknown) {
    thresholdError = caught instanceof Error ? caught.message : 'Некорректный порог'
  }

  const labels = settings.labels
    .split(',')
    .map((label) => label.trim())
    .filter(Boolean)

  function update(patch: Partial<ModelSettings>): void {
    onSettingsChange({ ...settings, ...patch })
  }

  return (
    <section className="settings-card" aria-labelledby="models-heading">
      <h2 id="models-heading">3. Настройки моделей</h2>

      {loading && (
        <p className="field-hint" role="status">
          Загружаем список моделей…
        </p>
      )}

      {loadError && (
        <div className="error-banner" role="alert">
          <p>{loadError}</p>
          <button
            className="button button-outline"
            type="button"
            disabled={disabled || loading}
            onClick={onReload}
          >
            Повторить загрузку
          </button>
        </div>
      )}

      {!loading && !loadError && !gliner && !wikineural && (
        <p className="field-error" role="alert">
          В каталоге нет поддерживаемых моделей. Запуск недоступен.
        </p>
      )}

      <fieldset className="fields-group" disabled={locked}>
        <legend className="field-label">Модели обработки</legend>

        <div className="model-options">
          {gliner && (
            <label className="model-option">
              <input
                type="checkbox"
                checked={settings.gliner}
                onChange={(event) => update({ gliner: event.target.checked })}
              />
              <span>
                <strong>{gliner.name}</strong>
                <span className="model-description">{gliner.description}</span>
              </span>
            </label>
          )}

          {wikineural && (
            <label className="model-option">
              <input
                type="checkbox"
                checked={settings.wikineural}
                onChange={(event) => update({ wikineural: event.target.checked })}
              />
              <span>
                <strong>{wikineural.name}</strong>
                <span className="model-description">{wikineural.description}</span>
              </span>
            </label>
          )}
        </div>

        {!loading &&
          !loadError &&
          (gliner || wikineural) &&
          !settings.gliner &&
          !settings.wikineural && <p className="field-error">Выберите хотя бы одну модель</p>}

        {settings.gliner && gliner && (
          <div className="field-block">
            <label className="field-label" htmlFor="entity-labels">
              Типы сущностей GLiNER
            </label>

            <input
              id="entity-labels"
              className={`text-input ${labels.length === 0 ? 'input-error' : ''}`}
              value={settings.labels}
              placeholder="person, organization, city"
              aria-invalid={labels.length === 0}
              aria-describedby="labels-hint"
              onChange={(event) => update({ labels: event.target.value })}
            />

            <p id="labels-hint" className="field-hint">
              Укажите типы через запятую. Например: person, organization, city.
            </p>

            {labels.length === 0 && (
              <p className="field-error">Укажите хотя бы один тип сущности</p>
            )}
          </div>
        )}

        <div className="threshold-row">
          <div>
            <label className="field-label" htmlFor="threshold-slider">
              Порог уверенности сущности
            </label>

            <input
              id="threshold-slider"
              className="threshold-slider"
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={sliderValue}
              aria-describedby="threshold-hint"
              onChange={(event) => update({ threshold: event.target.value })}
            />
          </div>

          <div>
            <label className="field-label" htmlFor="threshold-value">
              Значение
            </label>

            <input
              id="threshold-value"
              className={`text-input ${thresholdError ? 'input-error' : ''}`}
              type="text"
              inputMode="decimal"
              value={settings.threshold}
              aria-invalid={Boolean(thresholdError)}
              aria-describedby="threshold-error threshold-hint"
              onChange={(event) => update({ threshold: event.target.value })}
            />
          </div>
        </div>

        <div id="threshold-error" aria-live="polite">
          {thresholdError && <p className="field-error">{thresholdError}</p>}
        </div>

        <p id="threshold-hint" className="field-hint">
          Значение от 0 до 1. Предлагаемое назначение — минимальная уверенность извлечённой
          сущности. Это не схожесть текстов; применение порога ещё согласуется с ML.
        </p>

        <div className="field-block">
          <label className="field-label" htmlFor="max-depth">
            Максимальная глубина
          </label>

          <select
            id="max-depth"
            className="text-input depth-select"
            value={settings.maxDepth}
            onChange={(event) => update({ maxDepth: Number(event.target.value) })}
          >
            {[1, 2, 3, 4, 5].map((depth) => (
              <option key={depth} value={depth}>
                {depth}
              </option>
            ))}
          </select>

          <p className="field-hint">Число волн расширения после обработки начальных записей.</p>
        </div>
      </fieldset>
    </section>
  )
}
