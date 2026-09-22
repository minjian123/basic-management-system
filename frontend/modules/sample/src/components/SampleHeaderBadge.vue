<script setup lang="ts">
// 页头徽标（页面区域件）：展示模块运行期状态（只读消费宿主注入上下文的结果）。
import { computed } from 'vue'

import { useSampleI18n } from '../composables/useSampleI18n'
import { sampleRuntime } from '../runtime'

const { t } = useSampleI18n()
const state = sampleRuntime()

const label = computed(() => (state.canEdit ? t('sample.header.ready') : t('sample.header.readonly')))
const hint = computed(() => (state.permissionCount > 0 ? t('sample.header.permissions', { count: state.permissionCount }) : ''))
</script>

<template>
  <span class="sample-header-badge" :title="hint" data-test="sample-header-badge">
    <span class="sample-header-badge__dot" />
    {{ label }}
  </span>
</template>

<style scoped>
.sample-header-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 10px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-base);
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}
.sample-header-badge__dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--bms-sample-accent);
}
</style>
