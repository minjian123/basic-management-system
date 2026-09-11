/** 统一响应、分页与公共实体契约类型（手写基类；OpenAPI 生成类型随 05 域契约接入后并入）。 */

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

/** 公共实体字段：id 用 string（雪花 BIGINT 超出 JS 安全整数，JSON 边界以字符串传输）。 */
export interface BaseEntity {
  id: string
  createdAt: string
  updatedAt: string
}

/** 分页查询参数基类（list 接口 query 统一继承）。 */
export interface BasePageQuery {
  page: number
  size: number
}
