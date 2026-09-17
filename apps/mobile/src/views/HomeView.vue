<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

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
  <main class="home">
    <h1>{{ t('app.title') }}</h1>
    <p v-if="connected">{{ t('app.backend') }}：{{ name }} {{ version }}</p>
    <p v-else>{{ t('app.backendOffline') }}</p>
  </main>
</template>
