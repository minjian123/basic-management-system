/**
 * 多标签导航公共类型。
 */

import type { TabItem } from '@/components/base/tabs'

/** 标签项（片段 `TabItem` 的呈现扩展） */
export interface TabNavItem extends TabItem {
  /** 路由 path（点击导航用） */
  path?: string
  /** 图标（IconDisplay 回补前不渲染） */
  icon?: string
  /** 脏数据标记（关闭确认） */
  dirty?: boolean
  /** 角标（通知口径） */
  badge?: string | number
}
