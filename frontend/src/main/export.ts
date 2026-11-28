import { app, dialog, ipcMain, shell } from 'electron'
import type { BrowserWindow, IpcMainInvokeEvent } from 'electron'
import { writeFile } from 'node:fs/promises'
import { basename, dirname, extname, join } from 'node:path'
import type { SaveCsvResult } from '../shared/export'

export function registerExportHandlers(getWindow: () => BrowserWindow | undefined): void {
  let lastFolder: string | undefined
  let saving = false

  function senderWindow(event: IpcMainInvokeEvent): BrowserWindow {
    const window = getWindow()
    if (
      !window ||
      event.sender !== window.webContents ||
      event.senderFrame !== window.webContents.mainFrame
    ) {
      throw new Error('Недоступная команда')
    }
    return window
  }

  ipcMain.handle(
    'export:save-csv',
    async (event, filename: unknown, contents: unknown): Promise<SaveCsvResult> => {
      const window = senderWindow(event)
      if (
        typeof filename !== 'string' ||
        !/^.{1,120}\.csv$/i.test(filename) ||
        /[<>:"/\\|?*]/.test(filename) ||
        Array.from(filename).some((character) => character.charCodeAt(0) < 32) ||
        typeof contents !== 'string' ||
        Buffer.byteLength(contents, 'utf8') > 64 * 1024 * 1024
      ) {
        return { status: 'error', message: 'Проверьте имя файла и объём данных.' }
      }
      if (saving) return { status: 'error', message: 'Окно сохранения уже открыто.' }
      saving = true

      try {
        const { canceled, filePath } = await dialog.showSaveDialog(window, {
          title: 'Сохранить результаты сбора',
          defaultPath: join(lastFolder ?? app.getPath('documents'), filename),
          filters: [{ name: 'CSV', extensions: ['csv'] }],
          properties: ['showOverwriteConfirmation']
        })
        if (canceled || !filePath) return { status: 'cancelled' }
        if (extname(filePath).toLowerCase() !== '.csv') {
          return { status: 'error', message: 'Сохраните файл с расширением .csv.' }
        }
        await writeFile(filePath, contents, 'utf8')
        lastFolder = dirname(filePath)
        return { status: 'saved', filename: basename(filePath), folder: lastFolder }
      } catch {
        return {
          status: 'error',
          message: 'Проверьте доступ к папке и закройте файл, если он открыт.'
        }
      } finally {
        saving = false
      }
    }
  )

  ipcMain.handle('export:open-folder', async (event): Promise<boolean> => {
    senderWindow(event)
    return lastFolder ? (await shell.openPath(lastFolder)) === '' : false
  })
}
