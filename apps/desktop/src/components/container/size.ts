/** 尺寸解析（容器组件类共享）：数字按 px，字符串原样，`undefined` 原样返回。 */

export function resolveSize(value: number | string | undefined): string | undefined {
  if (value === undefined) {
    return undefined
  }
  return typeof value === 'number' ? `${value}px` : value
}
