<script setup lang="ts">
// 租户切换件：顶栏入口（当前租户）+ 弹层列表（内嵌 TenantList）+ 切换确认 + 加载态；单租户整体隐藏。
import { computed, ref, watch } from 'vue'

import type { BaseNotice, BaseTheme, TenantSummary, TenantSwitchSteps } from '@bms/core'
import { useBaseTenant } from '../../composables/useBaseTenant'
import TenantList from './TenantList.vue'

interface Props {
  /** 当前租户。 */
  current?: TenantSummary
  /** 可切换租户列表。 */
  tenants?: TenantSummary[]
  /** 切换是否二次确认（缺省 `true`）。 */
  confirm?: boolean
  /** 租户多时是否可搜索（缺省 `true`）。 */
  searchable?: boolean
  /** 列表每页条数（0 表示不分页）。 */
  pageSize?: number
  /** 切换编排步骤（宿主注入）。 */
  steps?: TenantSwitchSteps
  /** 品牌重载协作者。 */
  theme?: BaseTheme
  /** 提示通知协作者。 */
  notice?: BaseNotice
  /** 外部加载态。 */
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  current: undefined,
  tenants: () => [],
  confirm: true,
  searchable: true,
  pageSize: 0,
  steps: undefined,
  theme: undefined,
  notice: undefined,
  loading: false,
})

const emit = defineEmits<{
  switch: [tenant: TenantSummary]
  switched: [tenant: TenantSummary]
  failed: [payload: { target: TenantSummary; message: string }]
}>()

const {
  tenant,
  current,
  tenants,
  multiTenant,
  switching,
  errorMessage,
  setTenants,
  setCurrent,
  setSteps,
  request,
  confirm,
  retry,
  reset,
} = useBaseTenant({
  tenants: props.tenants,
  current: props.current,
  steps: props.steps,
  confirmRequired: props.confirm,
  theme: props.theme,
  notice: props.notice,
})

/** 弹层展开态。 */
const open = ref(false)
/** 待确认目标租户。 */
const pending = ref<TenantSummary | undefined>(undefined)

watch(
  () => props.tenants,
  (value) => setTenants(value),
  { deep: true },
)
watch(
  () => props.current,
  (value) => setCurrent(value),
  { deep: true },
)
watch(
  () => props.steps,
  (value) => setSteps(value ?? {}),
  { deep: true },
)
watch(
  () => props.confirm,
  (value) => {
    tenant.confirmRequired = value
  },
)

/** 当前租户名称。 */
const currentName = computed(() => current.value?.name ?? '选择租户')
/** 是否显示切换入口。 */
const visible = computed(() => multiTenant.value && !props.loading)

/**
 * 选择租户：需确认时进入确认区，否则直接切换。
 *
 * @param tenant 目标租户。
 */
const onSelect = async (tenant: TenantSummary): Promise<void> => {
  emit('switch', tenant)
  const ok = await request(tenant.id)
  if (ok) {
    finish(tenant, true)
    return
  }
  if (switching.value || errorMessage.value !== '') {
    finish(tenant, false)
    return
  }
  pending.value = tenant
}

/** 确认切换。 */
const onConfirm = async (): Promise<void> => {
  const tenant = pending.value
  if (tenant === undefined) {
    return
  }
  pending.value = undefined
  const ok = await confirm(tenant.id)
  finish(tenant, ok)
}

/** 取消确认。 */
const onCancel = (): void => {
  pending.value = undefined
  reset()
}

/**
 * 收尾：成功关闭弹层并上抛，失败上抛。
 *
 * @param tenant 目标租户。
 * @param ok 是否成功。
 */
const finish = (tenant: TenantSummary, ok: boolean): void => {
  if (ok) {
    open.value = false
    emit('switched', tenant)
    return
  }
  emit('failed', { target: tenant, message: errorMessage.value })
}

/** 重试最近失败切换。 */
const onRetry = async (): Promise<void> => {
  const target = tenants.value.find((item) => item.id === current.value?.id) ?? tenants.value[0]
  const ok = await retry()
  if (!ok && target !== undefined) {
    emit('failed', { target, message: errorMessage.value })
  }
}
</script>

<template>
  <div v-if="visible" class="bms-tenant-switcher" data-test="tenant-switcher">
    <button
      type="button"
      class="bms-tenant-switcher__entry"
      data-test="tenant-switcher-entry"
      :disabled="switching || loading"
      @click="open = !open"
    >
      <span class="bms-tenant-switcher__name">{{ currentName }}</span>
      <span v-if="switching" class="bms-tenant-switcher__state" data-test="tenant-switcher-switching">切换中…</span>
      <span v-else class="bms-tenant-switcher__arrow">▾</span>
    </button>

    <div v-if="open" class="bms-tenant-switcher__panel" data-test="tenant-switcher-panel">
      <slot name="list" :tenants="tenants" :select="onSelect">
        <TenantList
          :tenants="tenants"
          :current-id="current?.id ?? ''"
          :searchable="searchable"
          :page-size="pageSize"
          @select="onSelect"
        />
      </slot>

      <div v-if="pending !== undefined" class="bms-tenant-switcher__confirm" data-test="tenant-switcher-confirm">
        <span>切换到「{{ pending.name }}」将重新加载，未保存修改将丢失。</span>
        <button type="button" data-test="tenant-switcher-confirm-ok" @click="onConfirm">确认切换</button>
        <button type="button" data-test="tenant-switcher-confirm-cancel" @click="onCancel">取消</button>
      </div>

      <div v-if="errorMessage !== ''" class="bms-tenant-switcher__error" data-test="tenant-switcher-error">
        <span>{{ errorMessage }}</span>
        <button type="button" data-test="tenant-switcher-retry" @click="onRetry">重试</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bms-tenant-switcher {
  position: relative;
  display: inline-flex;
}

.bms-tenant-switcher__entry {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 6px);
  padding: 4px 10px;
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-sm, 4px);
  background: var(--bms-color-bg, #ffffff);
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.bms-tenant-switcher__state,
.bms-tenant-switcher__arrow {
  color: var(--bms-color-text-secondary, #909399);
  font-size: 12px;
}

.bms-tenant-switcher__panel {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm, 6px);
  min-width: 240px;
  padding: var(--bms-spacing-md, 8px);
  border: 1px solid var(--bms-color-border, #dcdfe6);
  border-radius: var(--bms-radius-md, 6px);
  background: var(--bms-color-bg, #ffffff);
  box-shadow: var(--bms-shadow-md, 0 4px 16px rgba(0, 0, 0, 0.16));
  z-index: 30;
}

.bms-tenant-switcher__confirm,
.bms-tenant-switcher__error {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 6px);
  font-size: 12px;
}

.bms-tenant-switcher__error {
  color: var(--bms-color-danger, #f56c6c);
}
</style>
