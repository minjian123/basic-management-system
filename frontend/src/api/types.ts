/** 统一响应与分页契约类型（手写基类；OpenAPI 生成类型随 05 域契约接入后并入）。 */

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface PageResponse<T> {
  list: T[]
  total: number
  page: number
  size: number
}
