import http from './index'

export const getWorkspace = () => http.get('/workspace')
export const setWorkspace = (path) => http.put('/workspace', { path })
export const getRenderSettings = () => http.get('/workspace/render')
export const setRenderSettings = (payload) => http.put('/workspace/render', payload)
