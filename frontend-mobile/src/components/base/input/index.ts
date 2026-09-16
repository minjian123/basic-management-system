/**
 * 能力域出口：输入域基类（`BaseInput` / `useInputBase`）。
 *
 * 契约见《组件设计 · 输入域基类》；域基类组合既有片段（`useField` / `useInputControl`）
 * 与字段上下文机制（`useFieldContext`），框架无关（具体控件由子类接入）。
 */

export * from './useInputBase'
export { default as BaseInput } from './BaseInput.vue'
