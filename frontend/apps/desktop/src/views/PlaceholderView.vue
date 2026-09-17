<script setup lang="ts">
/**
 * 占位视图：占位菜单驱动演示（菜单路由指向本组件），随认证 / 菜单任务接入真实页面后替换。
 */

import { useI18n } from 'vue-i18n'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { EmptyState } from '@bms/ui-ep'

const route = useRoute()
const { t } = useI18n()

const text = computed(() => {
  const title = (route.meta.title as string | undefined) ?? ''
  const suffix = t('layout.placeholder')
  return title ? `${title} · ${suffix}` : suffix
})
</script>

<template>
  <EmptyState type="custom" :title="text" />
</template>
