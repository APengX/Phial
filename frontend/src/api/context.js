import http from './index'

// Per-document context folders. The home page binds local folders to a
// document; their text content gets spliced into the AI prompt for any
// conversation about that doc.

export const listContextFolders = (path) =>
  http.get('/context/folders', { params: { path } })

export const listAllContextFolders = () =>
  http.get('/context/folders/all')

export const addContextFolder = (path, folder) =>
  http.post('/context/folders', { path, folder })

// `axios.delete` defaults to query params; pass the body via `data` so the
// folder path (which may contain spaces/Unicode) goes through unmangled.
export const removeContextFolder = (path, folder) =>
  http.delete('/context/folders', { data: { path, folder } })
