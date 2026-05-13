import http from './index'

// Per-document context.
//
// Two layers:
//   1. *Bindings* — the home page attaches a local folder to a doc; this just
//      defines the "range" of files the picker can show.
//   2. *Picks*    — the editor picker chooses which individual files (inside
//      those bound folders, plus other workspace .html docs) actually get
//      spliced into the next AI prompt. Defaults are empty: binding alone
//      sends nothing.

// ---- bindings -----------------------------------------------------------
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

// ---- picks --------------------------------------------------------------
export const getContextPicks = (path) =>
  http.get('/context/picks', { params: { path } })

// Pass only what you want to change; omitted keys are left as-is server-side.
export const putContextPicks = (path, { folders, docs } = {}) => {
  const body = { path }
  if (folders !== undefined) body.folders = folders
  if (docs !== undefined) body.docs = docs
  return http.put('/context/picks', body)
}

export const listContextTree = (path, folder) =>
  http.get('/context/tree', { params: { path, folder } })

export const listWorkspaceDocs = (path) =>
  http.get('/context/workspace-docs', { params: path ? { path } : {} })
