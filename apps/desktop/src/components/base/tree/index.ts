/**
 * 能力域出口：树域基类（`BaseTree` / `useTreeBase`）。
 *
 * 契约见《组件设计 · 树域基类》；域基类组合既有片段（`useTreeData`），
 * 框架无关（具体树控件由子类接入）。
 */

export * from './useTreeBase'
export { default as BaseTree } from './BaseTree.vue'
