import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 30000 })

// Unwrap {success, data} / surface {success:false, error}.
http.interceptors.response.use(
  (resp) => {
    const body = resp.data
    if (body && typeof body === 'object' && 'success' in body) {
      if (body.success) return body.data
      return Promise.reject(new Error(body.error || 'request failed'))
    }
    return body
  },
  (err) => {
    const msg = err.response?.data?.error || err.message || 'network error'
    return Promise.reject(new Error(msg))
  }
)

export default http
