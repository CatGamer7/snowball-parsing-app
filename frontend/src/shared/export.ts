export type SaveCsvResult =
  | { status: 'saved'; filename: string; folder: string }
  | { status: 'cancelled' }
  | { status: 'error'; message: string }

export interface ExportApi {
  saveCsv: (filename: string, contents: string) => Promise<SaveCsvResult>
  openExportFolder: () => Promise<boolean>
}
