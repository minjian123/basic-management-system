/**
 * 能力域出口：编辑器域基类（`BaseEditor` / `useEditorBase`）。
 *
 * 契约见《组件设计 · 编辑器域基类》；域基类组合既有片段（`useEditorKernel`），
 * 框架无关（真实编辑器内核由 `loader` 注入、独立分包）。
 */

export * from './useEditorBase'
export { default as BaseEditor } from './BaseEditor.vue'
