import { app, shell, BrowserWindow, ipcMain, dialog } from 'electron'
import { join } from 'node:path'
import { electronApp, optimizer, is } from '@electron-toolkit/utils'
import { BackendProcess } from './backend'
import icon from '../../resources/icon.png?asset'

let mainWindow: BrowserWindow | undefined
let backend: BackendProcess | undefined
let quitting = false
let cleanupDone = false

async function createWindow(): Promise<void> {
  mainWindow = new BrowserWindow({
    width: 900,
    height: 670,
    show: false,
    autoHideMenuBar: true,
    ...(process.platform === 'linux' ? { icon } : {}),
    webPreferences: { preload: join(__dirname, '../preload/index.js'), sandbox: false }
  })
  mainWindow.on('ready-to-show', () => mainWindow?.show())
  mainWindow.on('closed', () => { mainWindow = undefined })
  mainWindow.webContents.setWindowOpenHandler((details) => {
    if (/^https?:\/\//i.test(details.url)) void shell.openExternal(details.url)
    return { action: 'deny' }
  })
  if (app.isPackaged) {
    await mainWindow.loadURL('http://127.0.0.1:8000/app/index.html')
  } else if (is.dev && process.env.ELECTRON_RENDERER_URL) {
    await mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL)
  } else {
    await mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow?.isMinimized()) mainWindow.restore()
    mainWindow?.focus()
  })
  app.whenReady().then(async () => {
    electronApp.setAppUserModelId('ru.tpu.snowball')
    app.on('browser-window-created', (_, window) => optimizer.watchWindowShortcuts(window))
    ipcMain.on('ping', () => console.log('pong'))
    backend = new BackendProcess((message) => {
      if (!quitting) {
        dialog.showErrorBox('SnowBall', `${message}\nЖурнал: ${backend?.logPath}`)
        app.quit()
      }
    })
    try {
      await backend.start()
      if (!quitting) await createWindow()
    } catch (error) {
      if (!quitting) {
        const message = error instanceof Error ? error.message : 'Не удалось открыть приложение.'
        dialog.showErrorBox('SnowBall', `${message}\nЖурнал: ${backend.logPath}`)
        app.quit()
      }
    }
    app.on('activate', () => {
      if (!quitting && BrowserWindow.getAllWindows().length === 0) void createWindow()
    })
  })
  app.on('before-quit', (event) => {
    if (!app.isPackaged || cleanupDone) return
    event.preventDefault()
    if (quitting) return
    quitting = true
    void (backend?.stop() ?? Promise.resolve()).finally(() => {
      cleanupDone = true
      app.quit()
    })
  })
  app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit()
  })
}
