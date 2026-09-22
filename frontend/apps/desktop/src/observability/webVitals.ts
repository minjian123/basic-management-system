/**
 * 核心 Web Vitals 采集（宿主单一落点；官方 `web-vitals`）。
 *
 * 采集 LCP / CLS / INP；页级指标按**回调时刻的活动模块**归属（在 `index.ts` 归属），
 * 非模块路由归 `platform`。浏览器不支持 PerformanceObserver 时静默降级（不采集，不报错）。
 */

import { onCLS, onINP, onLCP, type Metric } from 'web-vitals'

/**
 * 安装 Web Vitals 采集。
 *
 * @param report 指标回调（含指标名 / 值 / 评级）。
 */
export function installWebVitals(report: (metric: Metric) => void): void {
  try {
    onCLS(report)
    onINP(report)
    onLCP(report)
  } catch {
    // 浏览器能力缺失（无 PerformanceObserver 等）：静默降级，不阻断宿主
  }
}
