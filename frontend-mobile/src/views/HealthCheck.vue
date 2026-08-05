<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'

const router = useRouter()

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
  <div class="health">
    <van-nav-bar title="后端健康检查" fixed placeholder @click-left="router.push('/')" />

    <van-cell-group inset>
      <van-cell title="请求地址" value="/healthz" />
      <van-cell title="状态">
        <van-tag v-if="state === 'loading'" type="warning">检测中</van-tag>
        <van-tag v-else-if="state === 'success'" type="success">正常</van-tag>
        <van-tag v-else type="danger">异常</van-tag>
      </van-cell>
      <van-cell v-if="detail" title="响应内容" :value="detail" />
      <van-cell v-if="errorMessage" title="错误信息" :value="errorMessage" />
    </van-cell-group>

    <div class="actions">
      <van-button type="primary" block round :loading="state === 'loading'" @click="checkHealth">
        重新检测
      </van-button>
    </div>

    <p class="hint">
      dev 模式下 /healthz 已由 Vite proxy 转发到后端 8000 端口（见 vite.config.ts）。
    </p>
  </div>
</template>

<style scoped>
.actions {
  margin: 20px 16px;
}

.hint {
  margin: 0 16px;
  color: #969799;
  font-size: 12px;
  text-align: center;
}
</style>
