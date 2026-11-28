import { existsSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const frontend = resolve(dirname(fileURLToPath(import.meta.url)), '../..')
const python = join(
  frontend,
  '../backend/.venv',
  process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python'
)
if (!existsSync(python)) {
  console.error('FAIL: сначала подготовьте backend/.venv с зависимостями backend и GLiNER.')
  process.exit(1)
}

// Фиксируем адрес API при сборке, чтобы настоящий ключ ушёл только локальному backend.
const build = spawnSync(
  process.execPath,
  [join(frontend, 'node_modules/electron-vite/bin/electron-vite.js'), 'build'],
  {
    cwd: frontend,
    stdio: 'inherit',
    windowsHide: true,
    env: { ...process.env, VITE_API_URL: 'http://127.0.0.1:8000' }
  }
)
if (build.error || build.status !== 0) process.exit(build.status || 1)

const result = spawnSync(python, [join(frontend, 'e2e/live/run.py'), ...process.argv.slice(2)], {
  cwd: frontend,
  stdio: 'inherit',
  windowsHide: true,
  env: { ...process.env, PYTHONIOENCODING: 'utf-8', SNOWBALL_E2E_NODE: process.execPath }
})
if (result.error) console.error('FAIL: не удалось запустить live-проверку.')
process.exitCode = result.status ?? 1
