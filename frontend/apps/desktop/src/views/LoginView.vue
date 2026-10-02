<!-- 登录页（需求 05-1）：独立全屏页 + 居中单卡片（品牌区 / 表单区 / 第三方入口区）。
     布局依据《布局设计 · 登录页》；本地登录成功写会话并按守卫口径回跳，SSO 入口按租户 IdP 清单渲染。 -->
<script setup lang="ts">
import {
  CAPTCHA_REQUIRED_TEXT,
  defaultCaptchaPolicy,
  isAuthErrorCode,
  normalizeCaptchaPolicy,
  resolveAuthErrorText,
  resolveSafeRedirect,
  type CaptchaCredential,
  type CaptchaKind,
} from '@bms/core'
import { CaptchaField, createHttpCaptchaSource } from '@bms/ui-ep'
import { computed, onMounted, ref, shallowRef } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { ApiError } from '@/api/error'
import { fetchSsoProviders, login, ssoAuthorizeUrl, type SsoProviderItem } from '@/api/identity'
import { captchaSourceOptions } from '@/api/endpoints'
import { getTenantCode } from '@/api/tenant'
import { useSessionStore } from '@/stores/session'
import { notifyMustChangePassword } from '@/utils/feedback'
import { normalizeLoginTenant, pickLoginCaptchaKind, toLoginCaptcha, type LoginCaptchaInput } from '@/utils/login'
import { redirectTo } from '@/utils/navigation'

defineOptions({ name: 'LoginView' })

const router = useRouter()
const route = useRoute()
const session = useSessionStore()

/** 验证码数据源（HTTP 内建实现；未注入即占位零请求）。 */
const captchaSource = createHttpCaptchaSource(captchaSourceOptions())

/** 租户标识（可选；缺省回填已持久化值，可清空表示不携带）。 */
const tenantInput = ref(getTenantCode() ?? '')
/** 登录账号。 */
const account = ref('')
/** 登录口令（不回填、不落任何存储）。 */
const password = ref('')
/** 明文切换（仅组件内存态）。 */
const passwordVisible = ref(false)
/** 验证码受控值（图形 / 短信）。 */
const captchaCode = ref('')
/** 验证码凭证（件层延迟提交模式上抛）。 */
const captchaCredential = shallowRef<CaptchaCredential | undefined>(undefined)
/** 验证码形态（策略渠道首个可渲染形态；`null` 表示不可用 / 未加载）。 */
const captchaKind = ref<CaptchaKind | null>(null)
/** 验证码是否被策略强制（为真即初始显示）。 */
const captchaForced = ref(false)
/** 登录失败次数（大于 0 即显示验证码并强制）。 */
const failCount = ref(0)
/** 验证码重挂载键（一次性失效后取新挑战并清空输入）。 */
const captchaAttempt = ref(0)
/** 提交中态（防重复提交）。 */
const submitting = ref(false)
/** 表单级提示（错误 / 锁定 / 限流 / SSO 回调失败）。 */
const formError = ref('')
/** SSO 入口清单（空则不渲染第三方入口区）。 */
const ssoProviders = ref<SsoProviderItem[]>([])

/** 生效租户编码（输入归一；空表示由子域名或后端上下文解析）。 */
const tenant = computed(() => normalizeLoginTenant(tenantInput.value))

/** 是否显示验证码块（策略强制或首次失败后；形态不可用则不显示）。 */
const captchaVisible = computed(() => captchaKind.value !== null && (captchaForced.value || failCount.value > 0))

/** 提交按钮文案。 */
const submitText = computed(() => (submitting.value ? '登录中…' : '登 录'))

/**
 * 加载验证码场景策略（挂载一次）：决定形态与是否强制显示；失败静默降级为不显示。
 */
async function loadCaptchaPolicy(): Promise<void> {
  try {
    const raw = await captchaSource.policy?.({ scene: 'login' })
    const policy = normalizeCaptchaPolicy(raw ?? defaultCaptchaPolicy('login'), 'login')
    captchaKind.value = pickLoginCaptchaKind(policy.channels)
    captchaForced.value = policy.required
  } catch {
    captchaKind.value = null
    captchaForced.value = false
  }
}

/** 加载 SSO 入口清单（失败 / 为空即不渲染第三方入口区，不阻断本地登录）。 */
async function loadSsoProviders(): Promise<void> {
  try {
    const result = await fetchSsoProviders(tenant.value)
    ssoProviders.value = [...(result.items ?? [])].sort((left, right) => left.sort - right.sort)
  } catch {
    ssoProviders.value = []
  }
}

/** SSO 回调失败回显（`?error=` 错误码 + `?message=` 兜底）。 */
function showSsoFailure(): void {
  const raw = route.query.error
  if (typeof raw !== 'string' || raw === '') {
    return
  }
  const code = Number(raw)
  if (Number.isFinite(code) && isAuthErrorCode(code)) {
    formError.value = resolveAuthErrorText(code)
    return
  }
  const message = typeof route.query.message === 'string' ? route.query.message : ''
  formError.value = message !== '' ? message : resolveAuthErrorText(undefined)
}

/** 缓存件层上抛的验证码凭证。 */
function onCaptchaCredential(credential: CaptchaCredential): void {
  captchaCredential.value = credential
}

/** 刷新验证码块：清空输入与凭证并重挂载（取新挑战，一次性失效口径）。 */
function refreshCaptcha(): void {
  captchaCode.value = ''
  captchaCredential.value = undefined
  captchaAttempt.value += 1
}

/**
 * 取当前提交用的验证码凭证（归一为契约体）。
 *
 * @returns 契约凭证；凭证不完备返回 `undefined`。
 */
function currentCaptcha(): LoginCaptchaInput | undefined {
  const credential = captchaCredential.value
  if (credential === undefined || credential.captchaId === '') {
    return undefined
  }
  if (credential.kind !== 'slider' && (credential.code ?? '') === '') {
    return undefined
  }
  return toLoginCaptcha(credential)
}

/**
 * 登录失败处置：文案映射 + 验证码块出现 / 刷新。
 *
 * @param error 登录异常。
 */
function handleLoginFailure(error: unknown): void {
  const code = error instanceof ApiError ? error.code : undefined
  formError.value = resolveAuthErrorText(code)
  if (code === 20101 || code === 20102) {
    // 后端要求验证码 / 验证码已失效：确保验证码块出现（策略未加载时回落图形码兜底）。
    captchaKind.value ??= 'image'
    captchaForced.value = true
  }
  failCount.value += 1
  refreshCaptcha()
}

/** 提交登录。 */
async function onSubmit(): Promise<void> {
  if (submitting.value) {
    return
  }
  formError.value = ''
  const accountValue = account.value.trim()
  if (accountValue === '' || password.value === '') {
    formError.value = '请填写账号与密码'
    return
  }
  let captcha: LoginCaptchaInput | undefined
  if (captchaVisible.value) {
    captcha = currentCaptcha()
    if (captcha === undefined) {
      formError.value = CAPTCHA_REQUIRED_TEXT
      return
    }
  }

  submitting.value = true
  try {
    const result = await login({
      account: accountValue,
      password: password.value,
      tenant: tenant.value,
      ...(captcha === undefined ? {} : { captcha }),
    })
    session.signIn({ token: result.access_token, user: result.user, tenant: result.user.tenant ?? tenant.value })
    if (result.user.must_change_password) {
      notifyMustChangePassword()
    }
    await router.push(resolveSafeRedirect(route.query.redirect))
  } catch (error) {
    handleLoginFailure(error)
  } finally {
    submitting.value = false
  }
}

/**
 * SSO 登录：顶层跳转授权端点（后端 `302` 到外部 IdP）。
 *
 * @param provider IdP 入口清单项。
 */
function onSsoLogin(provider: SsoProviderItem): void {
  redirectTo(ssoAuthorizeUrl(provider.idp_key, tenant.value))
}

onMounted(() => {
  showSsoFailure()
  void loadCaptchaPolicy()
  void loadSsoProviders()
})
</script>

<template>
  <main class="login-view" data-test="login-view">
    <section class="login-view__card">
      <header class="login-view__brand">
        <h1 class="login-view__title">BMS 基础管理系统</h1>
        <p class="login-view__subtitle">统一认证入口</p>
      </header>

      <form class="login-view__form" data-test="login-form" @submit.prevent="onSubmit">
        <label class="login-view__field">
          <span class="login-view__label">租户标识</span>
          <input
            v-model="tenantInput"
            class="login-view__input"
            type="text"
            autocomplete="organization"
            placeholder="子域名部署可留空"
            data-test="login-tenant"
          />
        </label>

        <label class="login-view__field">
          <span class="login-view__label">账号</span>
          <input
            v-model="account"
            class="login-view__input"
            type="text"
            autocomplete="username"
            placeholder="请输入账号"
            data-test="login-account"
          />
        </label>

        <label class="login-view__field">
          <span class="login-view__label">密码</span>
          <span class="login-view__password">
            <input
              v-model="password"
              class="login-view__input"
              :type="passwordVisible ? 'text' : 'password'"
              autocomplete="new-password"
              placeholder="请输入密码"
              data-test="login-password"
            />
            <button
              type="button"
              class="login-view__toggle"
              :aria-label="passwordVisible ? '隐藏密码' : '显示密码'"
              data-test="login-password-toggle"
              @click="passwordVisible = !passwordVisible"
            >
              {{ passwordVisible ? '隐藏' : '显示' }}
            </button>
          </span>
        </label>

        <div v-if="captchaVisible" class="login-view__captcha" data-test="login-captcha">
          <captcha-field
            :key="captchaAttempt"
            v-model="captchaCode"
            :kind="captchaKind ?? 'image'"
            scene="login"
            :source="captchaSource"
            :ready="true"
            submit-mode="defer"
            @credential="onCaptchaCredential"
            @refresh="refreshCaptcha"
          />
        </div>

        <p v-if="formError !== ''" class="login-view__error" role="alert" data-test="login-error">
          {{ formError }}
        </p>

        <button type="submit" class="login-view__submit" :disabled="submitting" data-test="login-submit">
          {{ submitText }}
        </button>
      </form>

      <footer v-if="ssoProviders.length > 0" class="login-view__sso" data-test="login-sso">
        <p class="login-view__sso-title">其他登录方式</p>
        <div class="login-view__sso-list">
          <button
            v-for="provider in ssoProviders"
            :key="provider.idp_key"
            type="button"
            class="login-view__sso-item"
            data-test="login-sso-item"
            @click="onSsoLogin(provider)"
          >
            {{ provider.name }}
          </button>
        </div>
      </footer>
    </section>
  </main>
</template>

<style scoped>
.login-view {
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--bms-spacing-lg);
  background: var(--bms-color-fill);
}

.login-view__card {
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

.login-view__brand {
  text-align: center;
}

.login-view__title {
  margin: 0;
  font-size: 20px;
  color: var(--bms-color-text);
}

.login-view__subtitle {
  margin: var(--bms-spacing-xs) 0 0;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}

.login-view__form {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md);
}

.login-view__field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-xs);
}

.login-view__label {
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}

.login-view__input {
  box-sizing: border-box;
  width: 100%;
  height: 32px;
  padding: 0 var(--bms-spacing-md);
  color: var(--bms-color-text);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.login-view__password {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
}

.login-view__password .login-view__input {
  flex: 1;
  min-width: 0;
}

.login-view__toggle {
  flex: none;
  padding: 0 var(--bms-spacing-sm);
  height: 32px;
  color: var(--bms-color-primary);
  background: transparent;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  cursor: pointer;
}

.login-view__captcha {
  display: flex;
  flex-direction: column;
}

.login-view__error {
  margin: 0;
  font-size: 12px;
  color: var(--bms-color-danger);
}

.login-view__submit {
  height: 36px;
  color: var(--bms-color-white);
  background: var(--bms-color-primary);
  border: none;
  border-radius: var(--bms-radius-md);
  cursor: pointer;
}

.login-view__submit:disabled {
  cursor: not-allowed;
  opacity: 0.7;
}

.login-view__sso {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}

.login-view__sso-title {
  margin: 0;
  font-size: 12px;
  text-align: center;
  color: var(--bms-color-text-secondary);
}

.login-view__sso-list {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm);
  justify-content: center;
}

.login-view__sso-item {
  height: 32px;
  padding: 0 var(--bms-spacing-md);
  color: var(--bms-color-text);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  cursor: pointer;
}
</style>
