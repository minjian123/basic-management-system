<!-- 扫码登录页（需求 05-4）：独立全屏页 + 居中卡片（品牌区 + 扫码面板）。
     面板经二维码件渲染授权二维码，四态状态机由宿主状态源（真实取角 + 占位轮询）驱动；
     确认后按状态源给出的完成语义跳转 / 安全回跳（复用 05_02 / 05_03 链路），本页不自行注册路由。 -->
<script setup lang="ts">
import { resolveSafeRedirect, selectScannableProviders } from '@bms/core'
import { SsoQrLoginPanel, type SsoQrPanelProvider } from '@bms/ui-ep'
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { fetchSsoProviders } from '@/api/identity'
import { createHttpSsoQrSource } from '@/api/ssoQr'
import { useSessionStore } from '@/stores/session'
import { redirectTo } from '@/utils/navigation'

defineOptions({ name: 'QrLoginView' })

const router = useRouter()
const route = useRoute()
const session = useSessionStore()

/** 扫码登录状态源（宿主内建：真实取授权 URL + 占位轮询）。 */
const source = createHttpSsoQrSource()
/** 可扫码入口（企微 / 钉钉）。 */
const providers = ref<SsoQrPanelProvider[]>([])

/** 取可扫码入口（失败 / 为空即空态，不阻断返回登录）。 */
async function loadProviders(): Promise<void> {
  try {
    const result = await fetchSsoProviders()
    providers.value = selectScannableProviders(result.items ?? [])
  } catch {
    providers.value = []
  }
}

/**
 * 授权确认：带 `redirect` 则顶层跳转，否则会话就绪后安全回跳。
 *
 * @param payload 完成载荷（可选 `redirect`）。
 */
async function onConfirmed(payload: { redirect?: string }): Promise<void> {
  if (payload.redirect !== undefined && payload.redirect !== '') {
    redirectTo(payload.redirect)
    return
  }
  await session.ensureReady()
  await router.push(resolveSafeRedirect(route.query.redirect))
}

/** 返回账号登录（保留回跳目标）。 */
function onBack(): void {
  void router.push({ path: '/login', query: route.query })
}

onMounted(() => {
  void loadProviders()
})
</script>

<template>
  <main class="qr-login-view" data-test="qr-login-view">
    <section class="qr-login-view__card">
      <header class="qr-login-view__brand">
        <h1 class="qr-login-view__title">BMS 基础管理系统</h1>
        <p class="qr-login-view__subtitle">扫码登录</p>
      </header>

      <sso-qr-login-panel
        :providers="providers"
        :source="source"
        @confirmed="onConfirmed"
        @back="onBack"
      />
    </section>
  </main>
</template>

<style scoped>
.qr-login-view {
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--bms-spacing-lg);
  background: var(--bms-color-fill);
}

.qr-login-view__card {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-lg);
  box-sizing: border-box;
  width: 100%;
  max-width: 360px;
  padding: var(--bms-spacing-xl);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-lg);
  box-shadow: var(--bms-shadow-1);
}

.qr-login-view__brand {
  text-align: center;
}

.qr-login-view__title {
  margin: 0;
  font-size: 20px;
  color: var(--bms-color-text);
}

.qr-login-view__subtitle {
  margin: var(--bms-spacing-xs) 0 0;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}
</style>
