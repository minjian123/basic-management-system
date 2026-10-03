<script setup lang="ts">
// 平台内建区域项：用户详情「账号信息」Tab（平台自身注册，演示平台来源项与模块来源项同槽同排序）。
import { DescriptionList, StatusContainer } from '@bms/ui-ep'
import type { DescItem, StatusContainerState } from '@bms/ui-ep'
import { computed, onMounted, ref } from 'vue'

import { fetchCurrentUser, type UserSummary } from '@/api/identity'

defineOptions({ name: 'UserDetailBasicTab' })

const state = ref<StatusContainerState>('loading')
const summary = ref<UserSummary | null>(null)

/** 账号信息字段（与 identity `/auth/me` 契约同字段）。 */
const items: DescItem[] = [
  { key: 'username', label: '用户名' },
  { key: 'name', label: '显示名' },
  { key: 'tenant', label: '租户编码' },
  { key: 'locale', label: '语言偏好' },
  { key: 'timezone', label: '时区' },
  { key: 'must_change_password', label: '强制改密' },
]

/** 渲染数据（强制改密转展示文案）。 */
const data = computed<Record<string, unknown>>(() =>
  summary.value === null
    ? {}
    : { ...summary.value, must_change_password: summary.value.must_change_password ? '是' : '否' },
)

/** 加载当前用户概要（未登录 / 失败呈现错误态，不阻塞宿主页其余部分）。 */
async function load(): Promise<void> {
  state.value = 'loading'
  try {
    summary.value = await fetchCurrentUser()
    state.value = 'ready'
  } catch {
    summary.value = null
    state.value = 'error'
  }
}

onMounted(load)
</script>

<template>
  <status-container :status="state" :delay="0" :retryable="true" error-text="账号信息加载失败" @retry="load">
    <description-list :items="items" :data="data" :columns="2" plain-enabled />
  </status-container>
</template>
