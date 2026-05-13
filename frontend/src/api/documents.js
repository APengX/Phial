import http from './index'

export const getTree = () => http.get('/documents/tree')
export const listDocuments = () => http.get('/documents/list').then((d) => d.documents)
export const getDocument = (path) => http.get('/documents/content', { params: { path } })
export const createDocument = (payload) => http.post('/documents', payload)
export const saveDocument = (path, html) => http.put('/documents/content', { path, html })
export const renameDocument = (src, dst) => http.post('/documents/rename', { src, dst })
export const deleteDocument = (path) => http.delete('/documents', { params: { path } })
export const makeDir = (path) => http.post('/documents/mkdir', { path })
