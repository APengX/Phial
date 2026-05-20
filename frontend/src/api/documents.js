import http from './index'

export const getTree = () => http.get('/documents/tree')
export const listDocuments = () => http.get('/documents/list').then((d) => d.documents)
export const getDocument = (path) => http.get('/documents/content', { params: { path } })
export const createDocument = (payload) => http.post('/documents', payload)
export const saveDocument = (path, html) => http.put('/documents/content', { path, html })
export const renameDocument = (src, dst) => http.post('/documents/rename', { src, dst })
export const deleteDocument = (path) => http.delete('/documents', { params: { path } })
export const makeDir = (path) => http.post('/documents/mkdir', { path })

// Auto-link: scan for / apply links to other workspace documents.
export const autoLinkScan = (path, html) =>
  http.post('/documents/auto-link/scan', { path, html })
export const autoLinkApply = (path, html, picks) =>
  http.post('/documents/auto-link/apply', { path, html, picks })
// Workspace-wide: scan / apply across every document.
export const autoLinkScanAll = () => http.post('/documents/auto-link/scan-all', {})
export const autoLinkApplyAll = (groups) =>
  http.post('/documents/auto-link/apply-all', { groups })

export function uploadDocument(file, { dir } = {}) {
  const fd = new FormData()
  fd.append('file', file, file.name)
  if (dir) fd.append('dir', dir)
  return http.post('/documents/upload', fd, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}
