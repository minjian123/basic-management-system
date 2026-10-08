/**
 * 模块契约类型（微前端骨架）：模块清单 / 注册声明 / 宿主上下文 / 加载器接口。
 *
 * 框架无关；模块（含阶段五远端模块）与平台自身注册共用本契约。
 */

import type { ModuleApi } from '../contracts/module-api'

/** 模块清单。 */
export interface ModuleManifest {
  /** 模块名（小写字母开头，可含数字与连字符）。 */
  name: string
  /** 版本。 */
  version: string
  /** 入口（远端模块预留；阶段四本地模块可缺省）。 */
  entry?: string
  /** 模块契约版本（自报构建时平台契约版本；须与平台常量一致才可加载）。 */
  contractVersion: number
}

/** 模块路由声明。 */
export interface ModuleRouteDeclaration {
  /** 路径。 */
  path: string
  /** 路由名（缺省用路径）。 */
  name?: string
  /** 组件异步加载器。 */
  component: () => Promise<unknown>
  /** 路由元信息（`title` / `keepAlive` 等）。 */
  meta?: Record<string, unknown>
}

/** 模块页面区域（具名插槽）声明。 */
export interface ModuleRegionDeclaration {
  /** 命名空间键（`<模块名>:<区域项>`）。 */
  key: string
  /** 区域标识（点分，如 `layout.header`；具名插槽为 `{域}.{页面}.{区域}`）。 */
  area: string
  /** 挂接组件。 */
  component: unknown
  /** 同区域排序提示（缺省 0）。 */
  order?: number
  /** 展示名（`tabs` 形态页签标题；缺省取键）。 */
  title?: string
  /** 图标键（`tabs` 形态页签图标；经图标注册表解析，未登记不渲染）。 */
  icon?: string
  /** 权限码（单个或数组；缺省不限制——宿主按已持有权限码判定）。 */
  perm?: string | readonly string[]
  /** 权限判定模式（缺省 `any`）。 */
  permMode?: 'any' | 'all' | 'not'
  /** 显示条件谓词（同步；求值 `false` 即不渲染；抛错按不渲染处置）。 */
  when?: () => boolean
}

/**
 * 具名插槽上下文（宿主页注入；**只读**）。
 *
 * 非路由承载的宿主页（如表单框架的记录页签：角色表单「角色分配」页签）把作用实体标识等经
 * 区域插槽件的 `context` 传入，区域项组件经 `useModuleSlotContext()`（`@bms/ui-ep`）**只读取得**——
 * 宿主页与插件之间**不新增直接依赖**；未提供的键以 `undefined` 呈现，插件**自行降级**（不假定存在、不发起请求）。
 */
export type ModuleSlotContext = Readonly<Record<string, unknown>>

/** 模块主题令牌声明。 */
export interface ModuleThemeTokenDeclaration {
  /** 命名空间键（`<模块名>:<主题标识>`）。 */
  key: string
  /** 令牌映射（`--bms-*` 变量 → 值）。 */
  tokens: Record<string, string>
  /** 模式标注（`light` / `dark` / 品牌标识等）。 */
  mode?: string
}

/** 模块 i18n 文案包声明。 */
export interface ModuleI18nPackDeclaration {
  /** 命名空间键（`<模块名>:<语言标识小写>`）。 */
  key: string
  /** 文案映射（`msg_key` → 文案）。 */
  messages: Record<string, string>
}

/** 模块字段渲染器声明。 */
export interface ModuleFieldRendererDeclaration {
  /** 命名空间键（`<模块名>:<键>`）。 */
  key: string
  /** 渲染组件（组件对象或异步加载器）。 */
  component: unknown
  /** 字段类型（供按类型解析）。 */
  fieldType?: string
}

/** 模块注册声明。 */
export interface ModuleRegistration {
  /** 路由声明。 */
  routes?: ModuleRouteDeclaration[]
  /** 通用组件声明（组件名 → 组件）。 */
  components?: Record<string, unknown>
  /** 字段渲染器声明。 */
  fieldRenderers?: ModuleFieldRendererDeclaration[]
  /** 图标声明（图标名 → 资源）。 */
  icons?: Record<string, unknown>
  /** 工作台卡片声明。 */
  cards?: unknown[]
  /** 页面区域声明。 */
  regions?: ModuleRegionDeclaration[]
  /** 主题令牌声明。 */
  themeTokens?: ModuleThemeTokenDeclaration[]
  /** i18n 文案包声明。 */
  i18nPacks?: ModuleI18nPackDeclaration[]
}

/** 宿主注入上下文（**`token` 不入清单**，模块不得持久化凭据）。 */
export interface ModuleHostContext {
  /** 路由。 */
  router?: unknown
  /** 状态管理。 */
  store?: unknown
  /** 国际化。 */
  i18n?: unknown
  /** 当前用户。 */
  user?: unknown
  /** 当前租户。 */
  tenant?: unknown
  /**
   * 请求能力（模块经宿主请求层访问后端；服务前缀 / 令牌 / 错误解包 / 401 由宿主处理）。
   *
   * 模块**禁自建 HTTP 客户端 / 裸请求**；缺失时自行降级（不假定存在）。
   */
  api?: ModuleApi
}

/** 模块定义。 */
export interface ModuleDefinition {
  /** 模块清单。 */
  manifest: ModuleManifest
  /** 装配入口：接收宿主上下文并返回注册声明。 */
  setup: (context: ModuleHostContext) => ModuleRegistration | Promise<ModuleRegistration>
}

/** 已加载模块。 */
export interface LoadedModule {
  /** 模块清单。 */
  manifest: ModuleManifest
  /** 注册声明。 */
  registration: ModuleRegistration
}

/** 模块加载器接口（阶段五远端加载按同一接口实现）。 */
export interface ModuleLoader {
  /** 按模块名加载（返回清单与注册声明，不挂载；上下文由宿主注入且冻结）。 */
  load(name: string, context?: ModuleHostContext): Promise<LoadedModule>
  /** 挂载（登记已挂载状态）。 */
  mount(loaded: LoadedModule): void
  /** 卸载（幂等）。 */
  unmount(name: string): void
  /** 是否已挂载。 */
  isMounted(name: string): boolean
  /** 已挂载模块名（挂载顺序）。 */
  mountedNames(): string[]
}
