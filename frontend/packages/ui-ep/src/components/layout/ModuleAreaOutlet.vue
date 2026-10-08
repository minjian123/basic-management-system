<script setup lang="ts">
// 模块区域插槽：按区域标识渲染注册表中该区域的模块项（只读消费；空区域渲染为空，不兜底）。
// 形态：`inline`（缺省）容器内逐项渲染；`tabs` 每项一个页签（标题取展示名，图标经图标注册表解析）。
//
// **条目契约（`inline` 形态）**：区域是**一行高的窄容器**（如 `layout.header`），注册项必须是**紧凑件**
// （徽标 / 按钮 / 状态标签）——**整页/大面板请走页面路由，勿注册进区域**。即使误注册，`inline` 形态亦
// 施加尺寸约束（`max-height: 100%` + `overflow: hidden`）把超出部分裁掉，不再外溢污染宿主布局。
// （回归：演示模块曾把整页 `DemoToolbox` 注册进 `layout.header`，页面 DOM 溢出到顶栏之上、残留在框架页。）
import type { FrontendRegistries } from '@bms/core'
import { ElTabPane, ElTabs } from 'element-plus'

import { ref, watch } from 'vue'

import { provideModuleSlotContext, useModuleArea, type ModuleAreaItem } from '../../composables/useModuleArea'
import IconRenderer from '../interaction/IconRenderer.vue'

interface Props {
  /** 区域 / 具名插槽标识（点分，如 `sys.user.detail.tabs`）。 */
  area: string
  /** 宿主注册表集合。 */
  registries: FrontendRegistries
  /** 装配版本号（装配 / 释放后自增，用于重算）。 */
  revision?: number
  /** 形态（缺省 `inline`）。 */
  variant?: 'inline' | 'tabs'
  /** 已持有权限码（按权限显隐；缺省空集合）。 */
  permissionCodes?: string[]
  /**
   * 显式上下文（宿主页注入；区域项经 `useModuleSlotContext()` 只读取得）。
   *
   * 用于**非路由承载**的宿主页（表单框架记录页签等）；未声明即不注入（插件自行降级）。
   */
  context?: Record<string, unknown>
}

const props = withDefaults(defineProps<Props>(), {
  revision: 0,
  variant: 'inline',
  permissionCodes: () => [],
  context: undefined,
})

// 显式上下文（只读注入；未声明即不注入——区域项经 `useModuleSlotContext()` 取得 `undefined` 并自行降级）
provideModuleSlotContext(() => props.context)

const { hidden, items, resolve } = useModuleArea({
  area: () => props.area,
  registries: props.registries,
  revision: () => props.revision,
  permissionCodes: () => props.permissionCodes,
})

/** 当前激活页签（`tabs` 形态；装配变化后回落到首项）。 */
const activeTab = ref('')

watch(
  () => items.value.map((item) => item.key),
  (keys) => {
    if (!keys.includes(activeTab.value)) {
      activeTab.value = keys[0] ?? ''
    }
  },
  { immediate: true },
)

/**
 * 页签标题（缺省取键）。
 *
 * @param item 区域项。
 */
function tabTitle(item: ModuleAreaItem): string {
  return item.title ?? item.key
}
</script>

<template>
  <div v-show="!hidden" class="bms-module-area-outlet" :data-area="area" :data-variant="variant">
    <el-tabs v-if="variant === 'tabs'" v-model="activeTab" class="bms-module-area-tabs">
      <el-tab-pane v-for="item in items" :key="item.key" :name="item.key">
        <template #label>
          <span class="bms-module-area-tab-label">
            <!-- 未登记图标不渲染（`IconRenderer` 兜底位为空；仅开发态告警） -->
            <icon-renderer v-if="item.icon" :name="item.icon" :registry="registries.icon" fallback="" />
            {{ tabTitle(item) }}
          </span>
        </template>
        <component :is="resolve(item.component)" />
      </el-tab-pane>
    </el-tabs>
    <template v-else>
      <component :is="resolve(item.component)" v-for="item in items" :key="item.key" />
    </template>
  </div>
</template>

<style scoped>
.bms-module-area-outlet {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: var(--bms-space-1);
  min-width: 0;
}

.bms-module-area-outlet[data-variant='inline'] {
  /* 一行高区域的尺寸约束：条目超大（误注册整页）时裁掉，不外溢污染宿主布局 */
  max-height: 100%;
  overflow: hidden;
}

.bms-module-area-outlet[data-variant='tabs'] {
  display: block;
  width: 100%;
}

.bms-module-area-tabs {
  width: 100%;
}

.bms-module-area-tab-label {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-space-1);
}
</style>
