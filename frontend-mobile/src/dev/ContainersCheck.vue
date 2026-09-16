<script setup lang="ts">
/**
 * 容器件收口核对页（开发专用）：八件容器可视化 + 页面自检（运行时断言结果直接上屏，便于截图核对）。
 *
 * - 默认（或 `?stage=1`）：静态展示（首屏核对：懒加载占位 / 延迟窗口内不显示 loading）；
 * - `?stage=2`：自动演示交互后状态（虚拟列表跳索引、滚动容器触底、分区折叠、加载错误态、懒加载进入视口）。
 */

import { nextTick, onMounted, ref } from 'vue'

import {
  AspectRatio,
  AutoHeight,
  FullscreenContainer,
  LazyContainer,
  LoadingContainer,
  ScrollContainer,
  SectionContainer,
  VirtualList,
} from '@/components/container'

const checks = ref<Record<string, string>>({})
const reachBottomCount = ref(0)
const retryCount = ref(0)
const stateSwitch = ref<'content' | 'loading' | 'error' | 'empty'>('content')
const autoHeightRef = ref<{ height: number } | null>(null)
const fullscreenRef = ref<{ isFullscreen: boolean; isFallback: boolean; toggle: () => void } | null>(null)
const scrollRef = ref<{ scrollToBottom: () => void; scrollTop: number } | null>(null)
const virtualRef = ref<{ scrollToIndex: (index: number) => void } | null>(null)
const sectionCollapsed = ref(false)

const rows = Array.from({ length: 1000 }, (_, index) => ({ id: index + 1, text: `虚拟行 ${index + 1}` }))
const scrollLines = Array.from({ length: 80 }, (_, index) => `滚动行 ${index + 1}`)

function onReachBottom(): void {
  reachBottomCount.value += 1
}

function onRetry(): void {
  retryCount.value += 1
}

function switchState(next: typeof stateSwitch.value): void {
  stateSwitch.value = next
}

function onFullscreenChange(): void {
  requestAnimationFrame(() => {
    checks.value = {
      ...checks.value,
      全屏态: String(fullscreenRef.value?.isFullscreen ?? false),
      全屏降级态: String(fullscreenRef.value?.isFallback ?? false),
    }
  })
}

/** 样式表内是否存在宽高比降级规则（`@supports not (aspect-ratio …)`） */
function hasAspectSupportsRule(): boolean {
  for (const sheet of Array.from(document.styleSheets)) {
    try {
      for (const rule of Array.from((sheet as CSSStyleSheet).cssRules)) {
        if (rule instanceof CSSSupportsRule && rule.conditionText.includes('aspect-ratio')) {
          return true
        }
      }
    } catch {
      // 跨源样式表跳过
    }
  }
  return false
}

function runChecks(): void {
  const root = document.documentElement
  const styleOf = (name: string): string => getComputedStyle(root).getPropertyValue(name).trim()
  const virtualList = document.querySelector('.bms-virtual-list')
  const autoParent = document.querySelector('.auto-parent') as HTMLElement | null
  const aspect = document.querySelector('.bms-aspect-ratio') as HTMLElement | null
  const aspectRect = aspect?.getBoundingClientRect()
  checks.value = {
    虚拟列表渲染项数_期望不超过30: String(virtualList?.querySelectorAll('.bms-virtual-list-item').length ?? -1),
    虚拟列表撑高元素高_期望40000: String(
      (virtualList?.querySelector('.bms-virtual-list-spacer') as HTMLElement | null)?.style.height ?? '-',
    ),
    滚动容器_样式化类: String(document.querySelector('.bms-scroll-container--styled') !== null),
    滚动容器_哨兵数_期望2: String(document.querySelectorAll('.bms-scroll-container-sentinel').length),
    滚动容器_触底次数: String(reachBottomCount.value),
    滚动条令牌_期望8px: styleOf('--bms-scrollbar-size'),
    懒加载_占位骨架存在: String(document.querySelector('.bms-lazy-container-skeleton') !== null),
    懒加载_已渲染: String(document.querySelector('.lazy-real') !== null),
    自适应高度_期望_父高减offset: `${String(autoHeightRef.value?.height ?? -1)}（父 ${String(autoParent?.clientHeight ?? -1)} − offset 40）`,
    宽高比_比值_期望1_78: aspectRect ? (aspectRect.width / aspectRect.height).toFixed(2) : '-',
    宽高比_内联样式: aspect?.style.aspectRatio ?? '-',
    宽高比_降级规则存在_supports: String(hasAspectSupportsRule()),
    加载容器_loading态存在: String(
      document.querySelector('[data-testid="state-demo"] [data-testid="loading-state"]') !== null,
    ),
    加载容器_四态切换示例_当前: stateSwitch.value,
    加载容器_错误态存在: String(document.querySelector('[data-testid="error-state"]') !== null),
    分区_折叠态: sectionCollapsed.value ? '已折叠（内容移除）' : '展开',
    分区_内容存在: String(document.querySelector('[data-testid="section-content"]') !== null),
  }
}

onMounted(async () => {
  const stage = new URLSearchParams(window.location.search).get('stage') ?? '1'
  await new Promise((resolve) => requestAnimationFrame(() => resolve(null)))
  if (stage === '3') {
    // 自动演示：全屏（headless 无用户手势 → 走降级铺满路径）
    fullscreenRef.value?.toggle()
    await new Promise((resolve) => setTimeout(resolve, 400))
  }
  if (stage === '2') {
    // 自动演示：交互后状态
    virtualRef.value?.scrollToIndex(500)
    scrollRef.value?.scrollToBottom()
    sectionCollapsed.value = true
    stateSwitch.value = 'error'
    await nextTick()
    document.querySelector('.lazy-real')?.scrollIntoView({ block: 'center' })
    await new Promise((resolve) => setTimeout(resolve, 450))
  }
  runChecks()
})
</script>

<template>
  <div class="check-page">
    <h1>容器组件类 · 收口核对页（开发专用）</h1>

    <section class="card">
      <h2>页面自检（运行时断言，截图即证据）</h2>
      <ul class="checks">
        <li v-for="(value, key) in checks" :key="key">{{ key }}：{{ value }}</li>
      </ul>
      <p>触底事件次数：{{ reachBottomCount }}　重试次数：{{ retryCount }}</p>
    </section>

    <div class="grid">
      <section class="card">
        <h2>1 滚动容器（固定头/底 + 样式化滚动条）</h2>
        <ScrollContainer
          ref="scrollRef"
          :height="220"
          keep-position
          position-key="check-scroll"
          @reach-bottom="onReachBottom"
        >
          <template #header><div class="fixed">固定头</div></template>
          <div v-for="line in scrollLines" :key="line" class="line">{{ line }}</div>
          <template #footer><div class="fixed">固定底</div></template>
        </ScrollContainer>
      </section>

      <section class="card">
        <h2>3 虚拟列表容器（1000 行）</h2>
        <VirtualList ref="virtualRef" :items="rows" :item-height="40" :height="240" :buffer="3">
          <template #default="{ item }"><div class="line">{{ item.text }}</div></template>
        </VirtualList>
      </section>

      <section class="card">
        <h2>4 全屏容器（点击进入；失败降级铺满）</h2>
        <FullscreenContainer
          ref="fullscreenRef"
          :model-value="false"
          @fullscreen-change="onFullscreenChange"
        >
          <div class="fs-inner">
            <button type="button" @click="fullscreenRef?.toggle?.()">进入 / 退出全屏</button>
            <p>全屏态：{{ fullscreenRef?.isFullscreen ?? false }}　降级：{{ fullscreenRef?.isFallback ?? false }}</p>
          </div>
        </FullscreenContainer>
      </section>

      <section class="card">
        <h2>5 自适应高度（父高 − offset 40）</h2>
        <div class="auto-parent">
          <AutoHeight ref="autoHeightRef" :offset="40" :scroll="true">
            <div class="line">高度来自父剩余空间</div>
            <div v-for="line in scrollLines" :key="line" class="line">{{ line }}</div>
          </AutoHeight>
        </div>
      </section>

      <section class="card">
        <h2>6 宽高比容器（16 / 9，占位）</h2>
        <AspectRatio :ratio="'16/9'">
          <div class="ratio-content">16 / 9 占位内容</div>
        </AspectRatio>
      </section>

      <section class="card" data-testid="state-demo">
        <h2>7 加载遮罩容器（四态）</h2>
        <div class="row">
          <button type="button" @click="switchState('content')">content</button>
          <button type="button" @click="switchState('loading')">loading</button>
          <button type="button" @click="switchState('error')">error</button>
          <button type="button" @click="switchState('empty')">empty</button>
        </div>
        <LoadingContainer
          :loading="stateSwitch === 'loading'"
          :error="stateSwitch === 'error' ? '示例：加载失败（请重试）' : false"
          :empty="stateSwitch === 'empty'"
          @retry="onRetry"
        >
          <div class="line">四态切换示例内容</div>
        </LoadingContainer>
        <p>当前：{{ stateSwitch }}　重试次数：{{ retryCount }}</p>
      </section>

      <section class="card">
        <h2>7b 加载形态（delay=0 常显：mask / skeleton / spin）</h2>
        <div class="row">
          <span>mask</span>
          <LoadingContainer :loading="true" :delay="0" mode="mask" :min-height="70" />
          <span>skeleton</span>
          <LoadingContainer :loading="true" :delay="0" mode="skeleton" :min-height="70" />
          <span>spin</span>
          <LoadingContainer :loading="true" :delay="0" mode="spin" :min-height="70" />
        </div>
      </section>

      <section class="card">
        <h2>8 分区容器（轻量 + 折叠）</h2>
        <SectionContainer
          v-model:collapsed="sectionCollapsed"
          title="基本信息"
          description="账号与联系方式（轻量分区，无卡片外观）"
          collapsible
        >
          <template #extra><button type="button">工具区</button></template>
          <div class="line">分区内容（折叠时按需移除）</div>
        </SectionContainer>
        <p>折叠态：{{ sectionCollapsed }}</p>
      </section>

      <section class="card">
        <h2>9 懒加载容器（首屏视口外 → 占位骨架；长图核对已渲染）</h2>
        <LazyContainer :min-height="160">
          <div class="lazy-real">已渲染（进入视口后才可见）</div>
        </LazyContainer>
      </section>
    </div>
  </div>
</template>

<style scoped>
.check-page {
  padding: var(--bms-space-4);
  font-family: var(--bms-font-family);
  color: var(--bms-color-text);
  background: var(--bms-color-bg-page);
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(320px, 1fr));
  gap: var(--bms-space-4);
}

.card {
  padding: var(--bms-space-3);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.checks {
  columns: 2;
  margin: 0;
  padding-left: var(--bms-space-4);
  font-family: var(--bms-font-family-mono);
  font-size: var(--bms-font-size-sm);
}

.line {
  padding: var(--bms-space-1) 0;
  border-bottom: 1px dashed var(--bms-color-border);
}

.fixed {
  padding: var(--bms-space-2);
  background: var(--bms-color-bg-page);
}

.lazy-real {
  padding: var(--bms-space-4);
  background: color-mix(in srgb, var(--bms-color-success) 12%, transparent);
}

.auto-parent {
  height: 300px;
  padding: var(--bms-space-2);
  border: 1px dashed var(--bms-color-primary);
}

.ratio-content {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--bms-color-text-secondary);
}

.row {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin: var(--bms-space-2) 0;
}

.row > :deep(.bms-loading-container) {
  flex: 1;
}

.fs-inner {
  padding: var(--bms-space-4);
  background: var(--bms-color-bg);
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }

  .checks {
    columns: 1;
  }
}
</style>
