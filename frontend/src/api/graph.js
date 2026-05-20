import http from './index'

// Document relationship graph: { root, nodes, edges }.
export const getGraph = () => http.get('/documents/graph')
