<script setup lang="ts">
// 工作台卡片（示例数据概览）：读占位服务取总数并复用平台指标卡（声明即用，消费随工作台阶段）。
import { MetricCard } from '@bms/ui-ep'
import { onMounted, ref } from 'vue'

import { useSampleI18n } from '../composables/useSampleI18n'
import { sampleService } from '../services/sample-service'

const { t } = useSampleI18n()
const total = ref<number | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const page = await sampleService.list({ page: 1, size: 1 })
    total.value = page.total
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <metric-card
    ready
    :title="t('sample.card.title')"
    :value="total"
    :unit="t('sample.card.unit')"
    :loading="loading"
    :animate="false"
    data-test="sample-summary-card"
  />
</template>
