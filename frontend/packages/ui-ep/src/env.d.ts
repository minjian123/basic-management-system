/// <reference types="vite/client" />

/** SVG 资产模块声明（Vite 资源导入返回 URL）。 */
declare module '*.svg' {
  const source: string
  export default source
}
