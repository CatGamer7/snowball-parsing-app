import { contextBridge, ipcRenderer } from 'electron'
import type { ExportApi } from '../shared/export'
import { electronAPI } from '@electron-toolkit/preload'

// Custom APIs for renderer
const api: ExportApi = {
  saveCsv: (filename, contents) => ipcRenderer.invoke('export:save-csv', filename, contents),
  openExportFolder: () => ipcRenderer.invoke('export:open-folder')
}

// Use `contextBridge` APIs to expose Electron APIs to
// renderer only if context isolation is enabled, otherwise
// just add to the DOM global.
if (process.contextIsolated) {
  try {
    contextBridge.exposeInMainWorld('electron', electronAPI)
    contextBridge.exposeInMainWorld('api', api)
  } catch (error) {
    console.error(error)
  }
} else {
  // @ts-ignore (define in dts)
  window.electron = electronAPI
  // @ts-ignore (define in dts)
  window.api = api
}
