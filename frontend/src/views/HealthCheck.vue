<script setup lang="ts">
import { ref } from 'vue'

type HealthState = 'loading' | 'success' | 'error'

const state = ref<HealthState>('loading')
const detail = ref('')
const errorMessage = ref('')

async function checkHealth(): Promise<void> {
  state.value = 'loading'
  detail.value = ''
  errorMessage.value = ''
  try {
    const res = await fetch('/healthz', {
      headers: { Accept: 'text/plain' },
    })
    if (res.ok) {
      state.value = 'success'
      detail.value = await res.text()
    } else {
      state.value = 'error'
      detail.value = await res.text()
      errorMessage.value = `HTTP 状态码 ${res.status}`
    }
  } catch (error) {
    state.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : String(error)
  }
}

checkHealth()
</script>

<template>
  <el-card shadow="never" class="health-card">
    <template #header>
      <div class="card-header">
        <span>后端健康状态</span>
        <el-button size="small" type="primary" :loading="state === 'loading'" @click="checkHealth">
          重新检测
        </el-button>
      </div>
    </template>

    <div v-if="state === 'loading'" class="status-row">
      <el-tag type="info">检测中</el-tag>
      <span class="status-text">正在请求 /healthz …</span>
    </div>
    <div v-else-if="state === 'success'" class="status-row">
      <el-tag type="success">正常</el-tag>
      <span class="status-text">后端服务可用</span>
    </div>
    <div v-else class="status-row">
      <el-tag type="danger">异常</el-tag>
      <span class="status-text">后端服务不可用</span>
    </div>

    <p v-if="detail" class="detail">{{ detail }}</p>
    <p v-if="errorMessage" class="detail error">{{ errorMessage }}</p>

    <el-text size="small" type="info">
      说明：dev 模式下 /healthz 已由 Vite proxy 转发到后端 8000 端口（见 vite.config.ts 的
      server.proxy）；构建产物部署时请由网关/反向代理转发该路径。
    </el-text>
  </el-card>
</template>

<style scoped>
.health-card {
  max-width: 720px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.status-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-text {
  font-size: 14px;
}

.detail {
  margin: 12px 0 0;
  padding: 8px 12px;
  border-radius: 4px;
  background-color: #f5f7fa;
  font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
  font-size: 13px;
  word-break: break-all;
}

.detail.error {
  background-color: #fef0f0;
  color: #f56c6c;
}
</style>
