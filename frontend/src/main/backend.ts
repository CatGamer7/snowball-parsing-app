import { app } from 'electron'
import { spawn, execFile, type ChildProcess } from 'node:child_process'
import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, openSync, closeSync, statSync, renameSync } from 'node:fs'
import { get } from 'node:http'
import { createConnection } from 'node:net'
import { join } from 'node:path'

const API_URL = 'http://127.0.0.1:8000'

function portOccupied(): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = createConnection({ host: '127.0.0.1', port: 8000 })
    socket.setTimeout(1000)
    socket.once('connect', () => { socket.destroy(); resolve(true) })
    socket.once('error', () => { socket.destroy(); resolve(false) })
    socket.once('timeout', () => { socket.destroy(); resolve(true) })
  })
}

function healthMatches(instance: string): Promise<boolean> {
  return new Promise((resolve) => {
    const request = get(`${API_URL}/health`, { timeout: 1000 }, (response) => {
      let body = ''
      response.setEncoding('utf8')
      response.on('data', (chunk: string) => {
        body += chunk
        if (body.length > 4096) response.destroy()
      })
      response.on('error', () => resolve(false))
      response.on('close', () => resolve(false))
      response.on('end', () => {
        try {
          resolve(response.statusCode === 200 &&
            response.headers['x-snowball-instance'] === instance &&
            JSON.parse(body).status === 'ok')
        } catch { resolve(false) }
      })
    })
    request.on('timeout', () => request.destroy())
    request.on('error', () => resolve(false))
  })
}

export class BackendProcess {
  private child: ChildProcess | undefined
  private stopping = false
  private ready = false
  private startupError: Error | undefined
  readonly logPath = join(app.getPath('userData'), 'logs', 'backend.log')

  constructor(private readonly onUnexpectedExit: (message: string) => void) {}

  async start(): Promise<void> {
    if (!app.isPackaged) return
    if (await portOccupied()) {
      throw new Error('Порт 8000 занят. Закройте ранее запущенный SnowBall или отдельный бэкенд.')
    }
    const executable = join(process.resourcesPath, 'backend', 'snowball-backend.exe')
    const modelHub = join(process.resourcesPath, 'models', 'hub')
    const ui = join(process.resourcesPath, 'ui')
    if (!existsSync(executable) || !existsSync(modelHub) || !existsSync(join(ui, 'index.html'))) {
      throw new Error('Установка неполная: не найдены необходимые файлы. Переустановите SnowBall.')
    }
    mkdirSync(join(app.getPath('userData'), 'logs'), { recursive: true })
    if (existsSync(this.logPath) && statSync(this.logPath).size > 5 * 1024 * 1024) {
      try { renameSync(this.logPath, `${this.logPath}.old`) } catch { /* use current log */ }
    }
    const log = openSync(this.logPath, 'a')
    const instance = randomUUID()
    try {
      this.child = spawn(executable, [], {
        cwd: app.getPath('userData'),
        windowsHide: true,
        stdio: ['pipe', log, log],
        env: {
          ...process.env,
          SNOWBALL_PORT: '8000',
          SNOWBALL_INSTANCE_ID: instance,
          SNOWBALL_MANAGED: '1',
          SNOWBALL_DEVICE: 'cpu',
          SNOWBALL_MODEL_HUB: modelHub,
          SNOWBALL_UI_DIR: ui,
          HF_HOME: join(app.getPath('userData'), 'huggingface'),
          PYTHONUTF8: '1',
          PYTHONIOENCODING: 'utf-8'
        }
      })
    } finally { closeSync(log) }
    this.child.stdin?.on('error', () => { /* backend may have exited */ })
    this.child.on('error', (error) => { this.startupError = error })
    this.child.on('exit', (code) => {
      if (this.ready && !this.stopping) {
        this.onUnexpectedExit(`Сервис сбора завершился (код ${code ?? 'неизвестен'}).`)
      }
    })
    const deadline = Date.now() + 60_000
    while (Date.now() < deadline) {
      if (this.stopping) throw new Error('Запуск отменён.')
      if (this.startupError) throw this.startupError
      if (this.child.exitCode !== null || this.child.signalCode !== null) {
        throw new Error('Не удалось запустить сервис сбора. Подробности сохранены в журнале.')
      }
      if (await healthMatches(instance)) { this.ready = true; return }
      await new Promise((resolve) => setTimeout(resolve, 200))
    }
    throw new Error('Сервис сбора не ответил за 60 секунд. Подробности сохранены в журнале.')
  }

  async stop(): Promise<void> {
    this.stopping = true
    const child = this.child
    if (!child || child.exitCode !== null || child.signalCode !== null) return
    const exited = new Promise<void>((resolve) => child.once('exit', () => resolve()))
    let timer: ReturnType<typeof setTimeout> | undefined
    const timeout = new Promise<void>((resolve) => { timer = setTimeout(resolve, 8000) })
    child.stdin?.end('shutdown\n')
    try { await Promise.race([exited, timeout]) } finally { clearTimeout(timer) }
    if (child.exitCode === null && child.signalCode === null && child.pid) {
      if (process.platform === 'win32') {
        await new Promise<void>((resolve) => {
          execFile(join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'taskkill.exe'),
            ['/PID', String(child.pid), '/T', '/F'], { windowsHide: true, timeout: 5000 }, () => resolve())
        })
      } else { child.kill('SIGKILL') }
    }
  }
}
