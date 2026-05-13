import http from './index'

export const getAgents = () => http.get('/agents')
export const setAgent = (payload) => http.put('/agents', payload)
