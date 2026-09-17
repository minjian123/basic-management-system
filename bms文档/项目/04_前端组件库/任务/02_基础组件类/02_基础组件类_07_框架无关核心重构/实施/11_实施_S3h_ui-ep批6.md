# 框架无关核心重构 · S3h 实施记录（ui-ep 重建 · 批 6）：滚动基建与容器件

> 前端组件库 · 02 基础组件类 · 02-7 框架无关核心重构 · S3 阶段（批 6）实施记录

[文档首页](../../../../../../文档首页.md) › [02-7 框架无关核心重构](../02_基础组件类_07_框架无关核心重构.md) › 01 实施　|　[← 任务文档](../02_基础组件类_07_框架无关核心重构.md)

## 1. 实施信息 <a id="meta"></a>

| 项 | 值 |
| --- | --- |
| 阶段 | S3 `ui-ep` 插件重建 · 批 6（滚动基建 + 容器件 + `@bms/vue` 容器投影；累计迁入 32 件） |
| 实施日期 | 2026-09-16 |
| 实测工时 | ≈4.5h（6a ≈2h + 6b ≈2.5h） |
| 结论 | 批 6 完成：容器域 6 件迁移 + 滚动位置存储 / 虚拟范围随迁 + 容器投影补齐，全量 check 三包全绿 |

## 2. 交付物 <a id="deliverables"></a>

| 块 | 内容 |
| --- | --- |
| 滚动基建（6a） | `ScrollContainer`（header / footer 固定 + 滚动区；IO 哨兵触底 / 触顶（不可用降级 scroll 计算，进入一次 / 离开重置）；`keepPosition` 位置保持；leading + trailing 节流；暴露 `scrollTo*` / `scrollTop` / `el`）、`scrollPosition.ts`（内存 / session 适配器 + 存储工厂）、`size.ts`（`resolveSize`）、`types.ts`（滚动 / 虚拟度量与存储契约）、`useVirtualRange`（前缀和 + 二分，定高 / 动态高度统一路径） |
| 容器投影（新，`@bms/vue`） | `useContainer`：核心 `BaseContainer`（`collapsed` 状态机 + `subscribe` 桥接）↔ Vue；受控 / 非受控语义与旧实现同构；区域展示属性（`title` / `bordered` / `padding` / `columns` / `containerAttrs` / `hasSlot`）属绑定层 |
| 容器件（6b，5 件） | `SectionContainer`（折叠经容器投影）、`LoadingContainer`（mask / skeleton / spin + delay 防闪 + empty / error + retry）、`LazyContainer`（IO 触发；不可用降级即时渲染）、`AutoHeight`（父高 - offset + minHeight / maxHeight 裁剪；无父回退视口高）、`AspectRatio`（`aspect-ratio` 主路径 + padding-top 降级） |
| 用例（+14） | `tests/container-scroll.spec.ts`（8 条）：渲染与尺寸 / 滚动事件与触底触顶 / 位置保持 / 暴露方法 / 存储适配器 / `useVirtualRange` 定高与动态；`tests/container-parts.spec.ts`（6 条）：SectionContainer / LoadingContainer / LazyContainer / AutoHeight / AspectRatio |

## 3. 验证结果 <a id="verify"></a>

| 命令 | 结果 |
| --- | --- |
| `npm run check` | 全绿：core **41** + vue **3** + ui-ep **54** 用例，vue-tsc 无错 |

## 4. 问题与处置 <a id="issues"></a>

| 问题 | 处置 |
| --- | --- |
| 旧 `useContainer` 实现的受控语义（传 `collapsed` 即受控、内部变更只回调） | 投影层保留：核心承载状态，受控判定与 `onCollapseChange` 归绑定层；核心 `expand()` 无 `collapsible` 守卫与投影统一经 `setCollapsed` 守卫的差异已记录 |
| `LoadingContainer` 的 `delay` 防闪（默认非 0）与内部结构类名 | 用例传 `delay: 0` 断言即时 `loading` 态；空态 / 加载态以 `data-testid` 断言（非公开类名） |
| `LazyContainer` IO mock 的类型收窄（`let callback` 被 TS 收窄为 `null`） | 测试用 holder 对象持有回调（属性访问打破收窄），`vi.stubGlobal` 注入 MockIO |
| 容器域无 EP 依赖（纯自研 DOM / CSS） | 无 EP 显式导入需求；样式令牌（`--bms-scrollbar-*` 等）保持 |

## 5. 回写清单 <a id="writeback"></a>

| 文档 | 回写点 |
| --- | --- |
| [任务文档](../02_基础组件类_07_框架无关核心重构.md) | 状态行（S3 批 6）与阶段记录追加 |
| [计划](../../../../计划/01_计划_前端组件库.md) | §3 表 `02_07` 行（批 6 与累计 32 件、用例数） |
