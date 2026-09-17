# 框架无关核心重构 · S3j 实施记录（ui-ep 重建 · 批 7）：虚拟列表与全屏容器（S3 组件层完成）

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · S3 阶段（批 7）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | S3 `ui-ep` 插件重建 · 批 7（虚拟列表 + 全屏容器；**S3 组件层完成**，累计迁入 34 件） |
| 实施日期 | 2026-09-16 |
| 实测工时 | ≈1.5h |
| 结论 | 批 7 完成：容器域最后两件迁移；**旧组件目录（common/container/feedback/layout/menu/modal/tabs）全量迁入 `ui-ep`**，全量 check 三包全绿 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 迁移（2 件） | `VirtualList`（统一前缀和路径（定高 = 估值特例）+ 动态高度测量缓存 + rAF 调度滚动 + `scrollToIndex` pending 语义；复用已迁 `useVirtualRange` / `resolveSize`）、`FullscreenContainer`（`requestFullscreen` 原生路径 + CSS 降级（`isFallback`）+ 目标解析（self / document / 指定元素）+ expose `enter` / `exit` / `toggle`） |
| 用例（+5） | `tests/container-virtual.spec.ts`：VirtualList（可视范围切片（插槽项）/ 滚动度量与范围更新 / 暴露方法与 `scrollToIndex` 定位）、FullscreenContainer（降级路径 enter / exit / toggle（显式移除原生 API）/ 原生路径调用 `requestFullscreen`） |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run check` | 全绿：core **41** + vue **3** + ui-ep **59** 用例（合计 **103**），vue-tsc 无错 |

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 处置 |
| --- | --- |
| `VirtualList` 滚动经 `requestAnimationFrame` 调度（非同步 emit） | 用例 trigger 后加「等帧 + nextTick」辅助（`nextFrame`）再断言 |
| 项渲染经默认插槽（无插槽时项元素为空） | 用例以函数插槽渲染 `label` 文本；插槽参数类型按组件声明收口（`Record<string, unknown>`） |
| jsdom 提供 `requestFullscreen`（原生路径直接成功） | 降级用例显式移除 `Element.prototype.requestFullscreen`（`afterEach` 恢复原值） |

## 5. 回写清单 <a id="writeback"></a>

| 文档 | 回写点 |
| --- | --- |
| [任务文档](../02_基础组件类_07_框架无关核心重构.md) | 状态行（S3 组件层完成）与阶段记录追加 |
| [计划](../../../../计划/01_计划_前端组件库.md) | §3 表 `02_07` 行（批 7、S3 完成与累计 34 件、用例数） |
