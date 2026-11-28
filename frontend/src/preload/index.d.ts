import { ElectronAPI } from '@electron-toolkit/preload'
import type { ExportApi } from '../shared/export'

declare global {
  interface Window {
    electron: ElectronAPI
    api: ExportApi
  }
}
