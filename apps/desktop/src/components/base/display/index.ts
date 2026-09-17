/**
 * 能力域出口：展示域基类（`BaseDisplay` / `useDisplayBase`）。
 *
 * 契约见《组件设计 · 展示域基类》；域基类组合既有片段（`useDisplayControl` / `useValue`），
 * 框架无关（具体展示由子类接入）。
 */

export * from './useDisplayBase'
export { default as BaseDisplay } from './BaseDisplay.vue'
