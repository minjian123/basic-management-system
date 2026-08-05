import axios from 'axios'
import type { AxiosInstance } from 'axios'

// axios 封装骨架：后续按后端接口规范补充拦截器、错误码映射等
const http: AxiosInstance = axios.create({
  baseURL: '/api',
  timeout: 10_000,
})

http.interceptors.request.use(
  (config) => {
    return config
  },
  (error) => Promise.reject(error),
)

http.interceptors.response.use(
  (response) => response,
  (error) => Promise.reject(error),
)

export default http
