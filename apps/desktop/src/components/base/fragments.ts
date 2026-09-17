/**
 * 预置能力片段权威表：31 个片段的 `key` 与**片段→片段单向依赖**。
 *
 * 与《前端基类清单》「能力片段」节逐项对齐（清单为文档权威，本表为代码权威，二者由 `02_05` 对账）。
 * 模块加载即把已知片段登记到片段机制（`registerKnownFragments`），供开发态依赖校验使用。
 * **依赖只登记片段→片段的单向依赖**；节点正文中的「协作 / 消费」关系（如字段壳被渲染器调用）不入表。
 */

import { BaseCapability, registerKnownFragments } from '@/base/capability'

/** 片段 key 联合类型（新增片段 = 新增条目 + 登记，不扩充封闭枚举） */
export type FragmentKey = keyof typeof FRAGMENTS

/** 片段 key → 依赖片段（`depends`；空数组表示无片段依赖） */
export const FRAGMENTS = {
  // 形态 7
  interactive: [],
  'input-control': [],
  'display-control': [],
  container: [],
  'form-container': [],
  media: ['presigned-url'],
  layout: ['design-token'],
  // 值 · 字段链 4
  value: [],
  'field-shell': [],
  'field-perm': [],
  field: ['value', 'field-shell', 'field-perm'],
  // 选项源 1
  'option-source': ['value'],
  // 复用类 19
  'upload-engine': ['presigned-url'],
  'async-task': [],
  tabs: [],
  'persisted-state': [],
  'editor-kernel': [],
  'tree-data': [],
  'user-display': [],
  'dynamic-routes': [],
  'form-meta': [],
  'presigned-url': [],
  'drag-drop': [],
  'design-token': [],
  'form-page': [],
  locale: [],
  access: [],
  'column-config': ['persisted-state'],
  'query-scheme': ['persisted-state'],
  watermark: [],
  'fragment-context': [],
} as const satisfies Record<string, readonly string[]>

/** 预置片段 key 清单（31 个，保序） */
export const PRESET_FRAGMENT_KEYS = Object.keys(FRAGMENTS) as FragmentKey[]

/** 片段中文名（登记与调试用） */
export const FRAGMENT_LABELS: Record<FragmentKey, string> = {
  interactive: '交互片段',
  'input-control': '输入形态片段',
  'display-control': '展示形态片段',
  container: '容器片段',
  'form-container': '表单容器片段',
  media: '媒体片段',
  layout: '布局片段',
  value: '受控值片段',
  'field-shell': '字段壳片段',
  'field-perm': '字段权限片段',
  field: '字段编排片段',
  'option-source': '选项源片段',
  'upload-engine': '上传引擎片段',
  'async-task': '异步任务片段',
  tabs: '页签状态片段',
  'persisted-state': '偏好持久化片段',
  'editor-kernel': '编辑器内核片段',
  'tree-data': '树数据片段',
  'user-display': '用户展示片段',
  'dynamic-routes': '动态路由片段',
  'form-meta': '表单元数据片段',
  'presigned-url': '预签名片段',
  'drag-drop': '拖拽基座片段',
  'design-token': '设计令牌片段',
  'form-page': '表单页组合片段',
  locale: '语言上下文片段',
  access: '权限上下文片段',
  'column-config': '列配置片段',
  'query-scheme': '查询方案片段',
  watermark: '水印片段',
  'fragment-context': '片段上下文片段',
}

// 模块加载即登记（任何片段模块 import 本文件即可保证机制侧已知全表）
registerKnownFragments(FRAGMENTS)

/**
 * 声明并返回片段机制实例（各片段内部使用）。
 *
 * 返回的实例自带根系能力（`log` / `reportError` / `getConfig` / `t`），供片段输出开发态告警；
 * 开发态自动做一次依赖校验（依赖未登记 / 循环 / 非法 key 时告警）。
 */
export function declareFragment(key: FragmentKey, options: { depends?: readonly string[] } = {}): BaseCapability {
  const capability = new BaseCapability({
    ns: `fragment-${key}`,
    identifier: key,
    key,
    depends: [...(options.depends ?? FRAGMENTS[key])],
  })
  capability.assertDeps()
  return capability
}
