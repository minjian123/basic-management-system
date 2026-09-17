<script setup lang="ts">
/** 工作台（S5a 切流）：`@bms/ui-ep` 页面容器 + 卡片承载连通信息。 */

import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { Card, PageContainer } from '@bms/ui-ep'

import { fetchAppInfo } from '@/api/http'

const { t } = useI18n()
const name = ref('')
const version = ref('')
const connected = ref(false)

onMounted(async () => {
  try {
    const info = await fetchAppInfo()
    name.value = info.name
    version.value = info.version
    connected.value = true
  } catch {
    connected.value = false
  }
})
</script>

<template>
  <PageContainer :title="t('app.title')">
    <Card :title="t('app.backend')">
      <p v-if="connected">{{ name }} {{ version }}</p>
      <p v-else>{{ t('app.backendOffline') }}</p>
    </Card>
  </PageContainer>
</template>
