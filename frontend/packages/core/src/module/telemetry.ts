/**
 * 模块遥测记录与观测钩子（框架无关；见任务 03_03 详细设计 §3.1）。
 *
 * 记录三类事实：加载 / 渲染耗时（按阶段）、模块错误（携带模块名与版本）、Web Vitals（按活动模块归属）；
 * 采集侧（宿主）与汇总侧（遥测器）共用本形状，核心不触 DOM、不依赖框架。
 */

/** 模块加载 / 渲染阶段。 */
export type ModuleTelemetryPhase = 'resolve' | 'setup' | 'mount' | 'render'

/** 加载器内可观测阶段（解析入口 / 调用 setup）。 */
export type ModuleLoadPhase = 'resolve' | 'setup'

/** 加载 / 渲染耗时记录。 */
export interface ModuleLoadTimingRecord {
  /** 记录种类。 */
  kind: 'load'
  /** 模块名。 */
  name: string
  /** 模块版本。 */
  version: string
  /** 阶段。 */
  phase: ModuleTelemetryPhase
  /** 耗时（毫秒）。 */
  durationMs: number
  /** 是否成功。 */
  ok: boolean
  /** 记录时间（ISO）。 */
  at: string
}

/** 模块错误记录（携带模块名与版本；平台错误模块名为 `platform` / 版本为空）。 */
export interface ModuleErrorRecord {
  /** 记录种类。 */
  kind: 'error'
  /** 模块名（平台错误为 `platform`）。 */
  name: string
  /** 模块版本（平台错误为空串）。 */
  version: string
  /** 失败阶段。 */
  phase: string
  /** 失败原因（可读）。 */
  message: string
  /** 记录时间（ISO）。 */
  at: string
}

/** Web Vitals 记录（非模块路由归属 `platform`，故模块名 / 版本可空）。 */
export interface ModuleVitalRecord {
  /** 记录种类。 */
  kind: 'vital'
  /** 模块名（非模块路由为 `null`）。 */
  name: string | null
  /** 模块版本（非模块路由为 `null`）。 */
  version: string | null
  /** 指标名。 */
  metric: 'LCP' | 'CLS' | 'INP'
  /** 指标值（毫秒 / 无量纲）。 */
  value: number
  /** 评级（`good` / `needs-improvement` / `poor`）。 */
  rating: string
  /** 记录时间（ISO）。 */
  at: string
}

/** 遥测记录联合。 */
export type ModuleTelemetryRecord = ModuleLoadTimingRecord | ModuleErrorRecord | ModuleVitalRecord

/** 单模块遥测聚合（版本 / 加载耗时 / 错误 / Vitals）。 */
export interface ModuleTelemetryModuleGroup {
  /** 模块版本（取记录中的版本）。 */
  version: string
  /** 加载 / 渲染耗时记录。 */
  load: ModuleLoadTimingRecord[]
  /** 错误记录。 */
  errors: ModuleErrorRecord[]
  /** Vitals 记录。 */
  vitals: ModuleVitalRecord[]
}

/** 非模块（平台页面 / 清单获取失败等）遥测聚合。 */
export interface ModuleTelemetryPlatformGroup {
  /** 平台错误记录。 */
  errors: ModuleErrorRecord[]
  /** 平台 Vitals 记录。 */
  vitals: ModuleVitalRecord[]
}

/** 按模块聚合快照。 */
export interface ModuleTelemetrySnapshot {
  /** 模块名 → 模块聚合。 */
  modules: Record<string, ModuleTelemetryModuleGroup>
  /** 非模块（平台页面 / 清单获取失败等）错误与 Vitals。 */
  platform: ModuleTelemetryPlatformGroup
}

/** 加载观测钩子（加载器注入；缺省不观测）。 */
export interface ModuleLoadObserver {
  /**
   * 记录一个加载阶段的耗时（成败都记）。
   *
   * @param name 模块名。
   * @param version 模块版本。
   * @param phase 加载阶段。
   * @param durationMs 耗时（毫秒）。
   * @param ok 是否成功。
   */
  onPhase(name: string, version: string, phase: ModuleLoadPhase, durationMs: number, ok: boolean): void
}

/** 平台来源标识（非模块错误的模块名占位）。 */
export const PLATFORM_MODULE_NAME = 'platform'

/** 模块加载超时（整个 `load()` 计时；毫秒）。 */
export const MODULE_LOAD_TIMEOUT_MS = 10_000
