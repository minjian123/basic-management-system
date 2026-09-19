/**
 * 偏好项定义：分组与内置全量偏好项（标签 / 控件形态 / 选项）。
 *
 * 与核心 `domain/preference` 的偏好键一一对应；标签为界面文案（i18n 化随国际化任务）。
 */

import type { PreferenceKey } from '@bms/core'

/** 偏好项控件形态。 */
export type PreferenceControl = 'radio' | 'checkbox' | 'select' | 'switch'

/** 偏好项选项值（控件可接受的基本类型）。 */
export type PreferenceOptionValue = string | number | boolean

/** 偏好项选项。 */
export interface PreferenceOption {
  /** 选项文案。 */
  label: string
  /** 选项值。 */
  value: PreferenceOptionValue
}

/** 偏好项定义。 */
export interface PreferenceItem {
  /** 偏好项键。 */
  key: PreferenceKey
  /** 显示标签。 */
  label: string
  /** 控件形态。 */
  control: PreferenceControl
  /** 选项（`radio` / `select`）。 */
  options?: PreferenceOption[]
  /** 控件是否占满整行（`select` 常用）。 */
  block?: boolean
}

/** 偏好分组定义。 */
export interface PreferenceGroupDef {
  /** 分组键（用于分组裁剪）。 */
  key: string
  /** 分组标题。 */
  title: string
  /** 分组描述。 */
  description?: string
  /** 分组内偏好项。 */
  items: PreferenceItem[]
}

/** 内置全量偏好分组（对齐《组件设计 · 偏好设置面板》「偏好项（内置）」）。 */
export const DEFAULT_PREFERENCE_GROUPS: PreferenceGroupDef[] = [
  {
    key: 'appearance',
    title: '外观',
    items: [
      {
        key: 'themeMode',
        label: '主题模式',
        control: 'radio',
        options: [
          { label: '亮色', value: 'light' },
          { label: '暗色', value: 'dark' },
          { label: '跟随系统', value: 'system' },
        ],
      },
      { key: 'accent', label: '允许强调色覆盖', control: 'checkbox' },
    ],
  },
  {
    key: 'locale',
    title: '语言与时区',
    items: [
      {
        key: 'locale',
        label: '界面语言',
        control: 'select',
        block: true,
        options: [
          { label: '简体中文', value: 'zh-CN' },
          { label: 'English', value: 'en-US' },
        ],
      },
      {
        key: 'timezone',
        label: '时区',
        control: 'select',
        block: true,
        options: [
          { label: 'Asia/Shanghai (UTC+8)', value: 'Asia/Shanghai' },
          { label: 'UTC', value: 'UTC' },
        ],
      },
    ],
  },
  {
    key: 'layout',
    title: '布局',
    items: [
      { key: 'sidebarCollapsed', label: '侧栏默认折叠', control: 'checkbox' },
      { key: 'tabsEnabled', label: '启用多标签导航', control: 'checkbox' },
      {
        key: 'tabsStyle',
        label: '多标签样式',
        control: 'select',
        block: true,
        options: [
          { label: '卡片', value: 'card' },
          { label: '朴素', value: 'plain' },
        ],
      },
    ],
  },
  {
    key: 'density',
    title: '列表密度',
    items: [
      {
        key: 'listDensity',
        label: '列表密度',
        control: 'radio',
        options: [
          { label: '紧凑', value: 'compact' },
          { label: '舒适', value: 'comfortable' },
          { label: '宽松', value: 'loose' },
        ],
      },
    ],
  },
  {
    key: 'default',
    title: '默认主页',
    items: [
      {
        key: 'defaultRoute',
        label: '登录后默认页',
        control: 'select',
        block: true,
        options: [
          { label: '工作台', value: '/dashboard' },
          { label: '用户管理', value: '/user' },
          { label: '我的待办', value: '/wf/todo' },
        ],
      },
    ],
  },
  {
    key: 'notify',
    title: '通知偏好',
    items: [
      { key: 'notify.inbox', label: '站内信', control: 'checkbox' },
      { key: 'notify.email', label: '邮件', control: 'checkbox' },
      { key: 'notify.sms', label: '短信', control: 'checkbox' },
    ],
  },
  {
    key: 'shortcuts',
    title: '快捷键',
    items: [{ key: 'shortcuts', label: '启用快捷键', control: 'switch' }],
  },
]

/**
 * 解析生效分组（按 `groups` 裁剪；缺省使用内置全量分组）。
 *
 * @param groups 分组键清单（缺省全部）。
 * @returns 生效分组定义。
 */
export function resolvePreferenceGroups(groups?: string[]): PreferenceGroupDef[] {
  if (groups === undefined || groups.length === 0) {
    return DEFAULT_PREFERENCE_GROUPS
  }
  return DEFAULT_PREFERENCE_GROUPS.filter((group) => groups.includes(group.key))
}
