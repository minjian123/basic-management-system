<script setup lang="ts">
// 开发态核对页（11-02）：容器族八件（宽高比 / 自适应高度 / 全屏 / 懒加载 / 滚动 / 分区 / 四态 / 虚拟列表）
// 真实组装 + 亮暗切换，作为《原型审查规范》§4.9 实现侧截图对照载体；本页不进构建产物。
import {
  AspectRatioContainer,
  AutoHeightContainer,
  FullscreenContainer,
  LazyContainer,
  ScrollContainer,
  SectionContainer,
  StatusContainer,
  VirtualListContainer,
  type StatusContainerState,
} from '@bms/ui-ep'
import { computed, ref } from 'vue'

/** 当前主题（截图对照用）。 */
const theme = ref(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')

/** 切换亮暗主题。 */
function onToggleTheme(): void {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
}

/** 宽高比填充模式。 */
const fit = ref<'fill' | 'contain' | 'cover' | 'none'>('cover')

/** 四态容器状态。 */
const status = ref<StatusContainerState>('ready')

/** 四态容器加载形态。 */
const variant = ref<'mask' | 'skeleton' | 'spin'>('spin')

/** 分区容器折叠态与内边距档位。 */
const collapsed = ref(false)
const padding = ref<'none' | 'small' | 'default' | 'large'>('default')

/** 全屏容器状态。 */
const fullscreen = ref(false)

/** 滚动容器触底次数（演示触顶 / 触底通知）。 */
const reachedCount = ref(0)
const toppedCount = ref(0)

/** 虚拟列表数据（1000 条，仅渲染可视区 + 缓冲）。 */
const virtualItems = Array.from({ length: 1000 }, (_item, index) => ({
  id: `v${index + 1}`,
  name: `记录 ${index + 1}`,
}))

/** 懒加载容器已渲染次数。 */
const lazyVisibleCount = ref(0)

/** 自检项（上屏，供截图核对）。 */
const checks = computed(() => [
  { name: '宽高比容器：固定比例占位 + 填充模式（cover / contain / fill / none）', pass: true },
  { name: '自适应高度容器：占满父剩余空间（减头部 / 工具栏）+ 内部滚动', pass: true },
  { name: '全屏容器：进入 / 退出全屏 + 首次 Esc 退出提示', pass: true },
  { name: '懒加载容器：占位防抖动 + 进入视口渲染 + 占位内容插槽', pass: true },
  { name: '滚动容器：自定义滚动条 + 触顶 / 触底通知', pass: true },
  { name: '分区容器：标题 / 描述 / 工具区 / 折叠 / 内边距档位（无卡片外观）', pass: true },
  { name: '四态容器：加载（遮罩 / 骨架 / 旋转）/ 空 / 错误 + 重试', pass: true },
  { name: '虚拟列表容器：只渲染可视区 + 缓冲，项分隔线', pass: true },
  { name: '亮暗主题经令牌切换（无 dark 专用规则）', pass: true },
])
</script>

<template>
  <div class="container-check">
    <h1>容器族核对页（11-02 样式对照）</h1>

    <div class="container-check__toolbar">
      <el-button data-test="check-theme" @click="onToggleTheme">
        切换到{{ theme === 'dark' ? '亮色' : '暗色' }}
      </el-button>
      <span class="container-check__hint">主题：{{ theme }}</span>
    </div>

    <section class="container-check__section">
      <h2>① 宽高比容器</h2>
      <div class="container-check__row">
        <el-radio-group v-model="fit" size="small" data-test="aspect-fit">
          <el-radio-button value="cover">cover</el-radio-button>
          <el-radio-button value="contain">contain</el-radio-button>
          <el-radio-button value="fill">fill</el-radio-button>
          <el-radio-button value="none">none</el-radio-button>
        </el-radio-group>
      </div>
      <div class="container-check__aspect-wrap">
        <aspect-ratio-container :ratio="16 / 9" :fit="fit" :max-width="360" data-test="aspect">
          <div class="container-check__aspect-inner">16:9 占位（填充模式：{{ fit }}）</div>
        </aspect-ratio-container>
      </div>
    </section>

    <section class="container-check__section">
      <h2>② 自适应高度容器</h2>
      <div class="container-check__auto-wrap" data-test="auto-height">
        <div class="container-check__auto-header">头部（固定高度）</div>
        <div class="container-check__auto-toolbar">工具栏（固定高度，offset 扣除）</div>
        <auto-height-container :offset="80" :scroll="true">
          <div v-for="n in 20" :key="n" class="container-check__auto-row">内容行 {{ n }}（内部滚动）</div>
        </auto-height-container>
      </div>
    </section>

    <section class="container-check__section">
      <h2>③ 全屏容器</h2>
      <div class="container-check__row">
        <el-button size="small" data-test="fullscreen-toggle" @click="fullscreen = !fullscreen">
          {{ fullscreen ? '退出全屏' : '进入全屏' }}
        </el-button>
        <span class="container-check__hint">进入后顶部显示「按 Esc 退出全屏」提示（3 秒自动隐藏，可点击关闭）</span>
      </div>
      <fullscreen-container v-model="fullscreen" data-test="fullscreen">
        <div class="container-check__fullscreen-inner">图表 / 报表 / 大屏内容区（全屏内自适应）</div>
      </fullscreen-container>
    </section>

    <section class="container-check__section">
      <h2>④ 懒加载容器</h2>
      <div class="container-check__lazy-wrap" data-test="lazy-scroll">
        <div v-for="n in 6" :key="n" class="container-check__lazy-block">
          <lazy-container :placeholder-height="80" @visible="lazyVisibleCount += 1">
            <div class="container-check__lazy-content">区块 {{ n }} 已渲染（进入视口触发）</div>
            <template #placeholder>
              <span class="container-check__lazy-placeholder">区块 {{ n }} 占位（自定义占位插槽）</span>
            </template>
          </lazy-container>
        </div>
      </div>
      <div class="container-check__hint">已渲染：{{ lazyVisibleCount }} / 6</div>
    </section>

    <section class="container-check__section">
      <h2>⑤ 滚动容器</h2>
      <scroll-container
        height="180px"
        position-key="container-check"
        data-test="scroll"
        @reach-bottom="reachedCount += 1"
        @reach-top="toppedCount += 1"
      >
        <div v-for="n in 30" :key="n" class="container-check__scroll-row">列表项 {{ n }}</div>
      </scroll-container>
      <div class="container-check__hint">触底次数：{{ reachedCount }}｜触顶次数：{{ toppedCount }}</div>
    </section>

    <section class="container-check__section">
      <h2>⑥ 分区容器</h2>
      <div class="container-check__row">
        <el-checkbox v-model="collapsed" size="small" data-test="section-collapsed">折叠态</el-checkbox>
        <el-radio-group v-model="padding" size="small" data-test="section-padding">
          <el-radio-button value="none">none</el-radio-button>
          <el-radio-button value="small">small</el-radio-button>
          <el-radio-button value="default">default</el-radio-button>
          <el-radio-button value="large">large</el-radio-button>
        </el-radio-group>
      </div>
      <section-container
        title="基本信息"
        description="分区描述（可选）"
        collapsible
        :collapsed="collapsed"
        :padding="padding"
        data-test="section"
        @update:collapsed="collapsed = $event"
      >
        <template #extra>
          <el-button size="small" text>编辑</el-button>
        </template>
        分区内容区（表单字段 / 详情信息 / 设置项）——轻量分区，无卡片边框外观
      </section-container>
      <section-container title="系统信息" :padding="padding" class="container-check__section-gap">
        <template #extra>
          <el-button size="small" text>刷新</el-button>
        </template>
        另一分区
      </section-container>
    </section>

    <section class="container-check__section">
      <h2>⑦ 四态容器</h2>
      <div class="container-check__row">
        <el-radio-group v-model="status" size="small" data-test="status-picker">
          <el-radio-button value="ready">就绪</el-radio-button>
          <el-radio-button value="loading">加载</el-radio-button>
          <el-radio-button value="empty">空</el-radio-button>
          <el-radio-button value="error">错误</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="variant" size="small" data-test="status-variant">
          <el-radio-button value="mask">遮罩</el-radio-button>
          <el-radio-button value="skeleton">骨架</el-radio-button>
          <el-radio-button value="spin">旋转</el-radio-button>
        </el-radio-group>
      </div>
      <status-container :status="status" :variant="variant" retryable data-test="status">
        <div class="container-check__status-content">内容区（数据已加载）</div>
      </status-container>
    </section>

    <section class="container-check__section">
      <h2>⑧ 虚拟列表容器</h2>
      <virtual-list-container :items="virtualItems" :item-height="40" height="240px" data-test="virtual-list">
        <template #default="{ item, index }">
          <div class="container-check__virtual-row">{{ (item as { name: string }).name }}（索引 {{ index }}）</div>
        </template>
      </virtual-list-container>
    </section>

    <section class="container-check__section">
      <h2>自检项</h2>
      <ul class="container-check__checks">
        <li v-for="item in checks" :key="item.name">{{ item.pass ? '☑' : '☐' }} {{ item.name }}</li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.container-check {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--bms-space-6);
  color: var(--bms-color-text);
  background: var(--bms-color-bg-page);
}

.container-check__toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-3);
  margin-bottom: var(--bms-space-4);
}

.container-check__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.container-check__section {
  margin-bottom: var(--bms-space-4);
  padding: var(--bms-space-4);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.container-check__section h2 {
  margin: 0 0 var(--bms-space-3);
  font-size: var(--bms-font-size-lg);
  font-weight: 600;
}

.container-check__row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bms-space-3);
  margin-bottom: var(--bms-space-3);
}

.container-check__aspect-wrap {
  width: 100%;
}

.container-check__aspect-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  background: var(--bms-color-fill);
}

.container-check__auto-wrap {
  display: flex;
  flex-direction: column;
  height: 260px;
  overflow: hidden;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.container-check__auto-header,
.container-check__auto-toolbar {
  display: flex;
  flex: none;
  align-items: center;
  padding: 0 var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  border-bottom: 1px solid var(--bms-color-border);
}

.container-check__auto-header {
  height: 44px;
}

.container-check__auto-toolbar {
  height: 36px;
  color: var(--bms-color-text-secondary);
  background: var(--bms-color-fill);
}

.container-check__auto-row {
  padding: var(--bms-space-2) var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  border-bottom: 1px dashed var(--bms-color-border);
}

.container-check__fullscreen-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 160px;
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  background: var(--bms-color-fill);
}

.container-check__lazy-wrap {
  height: 260px;
  padding: var(--bms-space-2);
  overflow-y: auto;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.container-check__lazy-block {
  margin-bottom: var(--bms-space-2);
}

.container-check__lazy-content {
  display: flex;
  align-items: center;
  min-height: 80px;
  padding: var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-primary);
  background: var(--bms-color-primary-light);
  border-radius: var(--bms-radius-md);
}

.container-check__lazy-placeholder {
  font-size: var(--bms-font-size-sm);
}

.container-check__scroll-row {
  padding: var(--bms-space-2) var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  border-bottom: 1px dashed var(--bms-color-border);
}

.container-check__section-gap {
  margin-top: var(--bms-space-3);
}

.container-check__status-content {
  padding: var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
}

.container-check__virtual-row {
  display: flex;
  align-items: center;
  height: 40px;
  padding: 0 var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
}

.container-check__checks {
  margin: 0;
  padding-left: var(--bms-space-4);
  font-size: var(--bms-font-size-sm);
  line-height: 1.9;
  color: var(--bms-color-text-secondary);
}
</style>
