<script setup lang="ts">
// 开发态核对页（05_01 登录页）：三组 16 项自检（错误码文案 / 纯函数与地址 / 页面结构）程序化上屏；
// 页面结构项以真实挂载的登录页 DOM 核对；本页不进构建产物（`vite build` 只构建 `index.html`）。
import {
  DEFAULT_AUTH_ERROR_TEXT,
  configureRequestAdapter,
  isAuthErrorCode,
  resolveAuthErrorText,
  type RequestConfig,
} from '@bms/core'
import { nextTick, onMounted, ref } from 'vue'

import { ssoAuthorizeUrl } from '@/api/identity'
import { apiUrl } from '@/api/request'
import LoginView from '@/views/LoginView.vue'
import { normalizeLoginTenant, pickLoginCaptchaKind, toLoginCaptcha } from '@/utils/login'

/** 自检项。 */
interface CheckItem {
  /** 序号。 */
  no: number
  /** 说明。 */
  label: string
  /** 是否通过。 */
  ok: boolean
}

/** 自检分组。 */
interface CheckGroup {
  /** 分组标题。 */
  title: string
  /** 分组自检项。 */
  items: CheckItem[]
}

/** 桩 SSO 入口（核对入口渲染）。 */
const SSO_PROVIDER = { idp_key: 'keycloak', name: 'Keycloak', icon: '', type: 'oidc', sort: 1 }

/** 桩请求适配器调用轨迹（页面挂载期只应命中 SSO 清单）。 */
const requests: RequestConfig[] = []

/**
 * 构造桩响应（适配器返回已解包的 `data`）。
 *
 * @param value 数据体。
 * @returns 适配器返回值。
 */
function respond<T>(value: unknown): Promise<T> {
  return Promise.resolve(value as T)
}

// 桩适配器：SSO 清单返回一项，其余（验证码策略等）返回空——核对页不发真实请求。
configureRequestAdapter({
  request<T>(config: RequestConfig): Promise<T> {
    requests.push(config)
    if (config.url.includes('/auth/sso/providers')) {
      return respond<T>({ items: [SSO_PROVIDER] })
    }
    return respond<T>(undefined)
  },
})

/** 登录页宿主容器（页面结构自检的查询根）。 */
const host = ref<HTMLElement | null>(null)
/** 自检分组清单（挂载后填充）。 */
const groups = ref<CheckGroup[]>([])
/** 全部自检项。 */
const items = ref<CheckItem[]>([])
/** 通过项数。 */
const passed = ref(0)

/**
 * 在宿主容器内查询元素。
 *
 * @param selector CSS 选择器。
 * @returns 命中元素；未命中返回 `null`。
 */
function pick(selector: string): HTMLElement | null {
  return host.value === null ? null : host.value.querySelector<HTMLElement>(selector)
}

/**
 * 以原生 setter 写入输入值并派发 `input`（模拟用户输入，驱动件层受控值更新）。
 *
 * @param input 目标输入元素。
 * @param value 写入值。
 */
function fillInput(input: HTMLInputElement | null, value: string): void {
  if (input === null) {
    return
  }
  Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set?.call(input, value)
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

/** 等待挂载期异步（策略 / SSO 清单）落定并重渲染。 */
async function flush(): Promise<void> {
  await nextTick()
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

onMounted(async () => {
  const collected: CheckGroup[] = []
  let no = 0
  const add = (group: CheckGroup, label: string, ok: boolean): void => {
    no += 1
    group.items.push({ no, label, ok })
  }

  const errorText = resolveAuthErrorText(20002)
  const lockedText = resolveAuthErrorText(20003)
  const ssoDownText = resolveAuthErrorText(20053)
  const captchaText = resolveAuthErrorText(20101)
  const unknownText = resolveAuthErrorText(99999)
  const nonNumberText = resolveAuthErrorText('oops')

  const groupOne: CheckGroup = { title: '一、错误码文案与策略选形', items: [] }
  add(groupOne, `账号或密码错误（20002，实得 ${errorText}）`, errorText === '账号或密码错误')
  add(
    groupOne,
    `锁定 / IdP 故障文案（20003 → ${lockedText}；20053 → ${ssoDownText}）`,
    lockedText.includes('锁定') && ssoDownText.includes('外部登录服务不可用'),
  )
  add(groupOne, `验证码子段回落（20101 → ${captchaText}，复用验证码文案表）`, captchaText === '验证码错误')
  add(
    groupOne,
    `未登记码 / 非数字回落通用文案（${unknownText} / ${nonNumberText}）；判定 20002=${String(isAuthErrorCode(20002))}、99999=${String(isAuthErrorCode(99999))}`,
    unknownText === DEFAULT_AUTH_ERROR_TEXT &&
      nonNumberText === DEFAULT_AUTH_ERROR_TEXT &&
      isAuthErrorCode(20002) &&
      !isAuthErrorCode(99999),
  )
  add(
    groupOne,
    '策略渠道选形：slider 优先 / 跳过 sms 取 image / 仅 sms 或未下发即不显示',
    pickLoginCaptchaKind(['slider', 'image']) === 'slider' &&
      pickLoginCaptchaKind(['sms', 'image']) === 'image' &&
      pickLoginCaptchaKind(['image']) === 'image' &&
      pickLoginCaptchaKind(['sms']) === null &&
      pickLoginCaptchaKind(undefined) === null,
  )
  collected.push(groupOne)

  const imageCredential = toLoginCaptcha({ kind: 'image', captchaId: 'c1', code: 'ab12' })
  const sliderCredential = toLoginCaptcha({
    kind: 'slider',
    captchaId: 'c2',
    trace: [
      { x: 0, y: 0, t: 0 },
      { x: 96, y: 2, t: 140 },
    ],
  })
  const authorizeWithTenant = ssoAuthorizeUrl('keycloak', 'acme')
  const authorizeWithoutTenant = ssoAuthorizeUrl('keycloak', null)

  const groupTwo: CheckGroup = { title: '二、归一与地址构造', items: [] }
  add(
    groupTwo,
    '租户标识归一：去首尾空白，空串 / 未填即不携带',
    normalizeLoginTenant(' acme ') === 'acme' &&
      normalizeLoginTenant('') === null &&
      normalizeLoginTenant(undefined) === null,
  )
  add(
    groupTwo,
    `凭证归一：图形带 code（${imageCredential.captcha_id} / ${imageCredential.kind}），滑块轨迹转二元组（${JSON.stringify(sliderCredential.trace ?? [])}）`,
    imageCredential.code === 'ab12' &&
      imageCredential.kind === 'image' &&
      sliderCredential.trace !== undefined &&
      sliderCredential.trace.length === 2 &&
      sliderCredential.trace[1]?.[2] === 140,
  )
  add(
    groupTwo,
    `SSO 授权地址构造（含 tenant：${authorizeWithTenant}；无 tenant：${authorizeWithoutTenant}）`,
    authorizeWithTenant === `${apiUrl('identity', '/auth/sso/keycloak/authorize')}?tenant=acme` &&
      authorizeWithoutTenant === apiUrl('identity', '/auth/sso/keycloak/authorize'),
  )
  collected.push(groupTwo)

  await flush()

  const root = pick('[data-test="login-view"]')
  const tenantInput = pick('[data-test="login-tenant"]') as HTMLInputElement | null
  const accountInput = pick('[data-test="login-account"]') as HTMLInputElement | null
  // `data-test` 落点差异：`TextInput` 根即 Element Plus 输入框（属性透传到内部原生 input），
  // `PasswordInput` 根为包装 div（须再取内部 input）。
  const passwordInput = pick('[data-test="login-password"] input') as HTMLInputElement | null
  const submit = pick('[data-test="login-submit"]')
  const libraryInputs = host.value === null ? [] : [...host.value.querySelectorAll('.bms-text-input, .bms-password-input')]
  const nakedInputs =
    host.value === null
      ? []
      : [...host.value.querySelectorAll('input')].filter(
          (input) => input.closest('.bms-text-input, .bms-password-input') === null,
        )
  const buttons = host.value === null ? [] : [...host.value.querySelectorAll('button')]
  const ssoItems = host.value === null ? [] : host.value.querySelectorAll('[data-test="login-sso-item"]')

  const groupThree: CheckGroup = { title: '三、页面结构', items: [] }
  add(
    groupThree,
    '独立全屏页：登录页根元素存在且不含主框架（无侧栏 / 多标签）',
    root !== null &&
      host.value?.querySelector('.main-layout') === null &&
      host.value?.querySelector('[data-test="layout-side"]') === null,
  )
  add(
    groupThree,
    '表单要素齐备：租户标识 / 账号 / 密码 / 提交按钮',
    tenantInput !== null && accountInput !== null && passwordInput !== null && submit !== null,
  )
  add(
    groupThree,
    `表单件复用组件库：文本 / 密码件 ${libraryInputs.length} 个，裸原生 input ${nakedInputs.length} 个 / 非 Element Plus 按钮 ${buttons.filter((button) => !button.classList.contains('el-button')).length} 个`,
    libraryInputs.length === 3 &&
      nakedInputs.length === 0 &&
      buttons.length > 0 &&
      buttons.every((button) => button.classList.contains('el-button')),
  )
  add(
    groupThree,
    `密码安全口径：type=${passwordInput?.type ?? '无'} / 初值${(passwordInput?.value ?? '') === '' ? '为空' : '非空'} / autocomplete=${passwordInput?.getAttribute('autocomplete') ?? '无'}`,
    passwordInput?.type === 'password' &&
      passwordInput.value === '' &&
      passwordInput.getAttribute('autocomplete') === 'new-password',
  )
  // 明文切换图标（Element Plus `show-password`）仅在有值时渲染，故先填写口令再取图标并切换。
  fillInput(passwordInput, 'secret')
  await nextTick()
  const toggle = pick('[data-test="login-password"] .el-input__password')
  const typeBeforeToggle = passwordInput?.type ?? ''
  toggle?.click()
  await nextTick()
  const typeAfterToggle = passwordInput?.type ?? ''
  toggle?.click()
  await nextTick()
  const typeAfterRestore = passwordInput?.type ?? ''
  add(
    groupThree,
    `明文切换仅改输入类型（组件库件图标，${typeBeforeToggle} → ${typeAfterToggle} → ${typeAfterRestore}）`,
    toggle !== null && typeBeforeToggle === 'password' && typeAfterToggle === 'text' && typeAfterRestore === 'password',
  )
  const pageText = host.value?.textContent ?? ''
  add(
    groupThree,
    '无「记住我」开关、无密码强度提示（口径成文，归 05-5 / 改密场景）',
    !pageText.includes('记住我') && !pageText.includes('强度'),
  )
  add(
    groupThree,
    `SSO 入口按清单渲染（${ssoItems.length} 项，首项 ${ssoItems[0]?.textContent?.trim() ?? '无'}）`,
    ssoItems.length === 1 && (ssoItems[0]?.textContent ?? '').includes(SSO_PROVIDER.name),
  )
  add(
    groupThree,
    '验证码块初始不渲染（策略未强制 / 未失败；时机分支由 tests/login-view.spec.ts 锁定）',
    pick('[data-test="login-captcha"]') === null,
  )
  collected.push(groupThree)

  groups.value = collected
  items.value = collected.flatMap((group) => group.items)
  passed.value = items.value.filter((item) => item.ok).length
})
</script>

<template>
  <main class="check-page">
    <h1>登录页核对页（05_01 登录页真实实现）</h1>

    <section>
      <h2>自检清单</h2>
      <p>
        共 {{ items.length }} 项，通过
        <strong data-check-passed>{{ passed }}</strong>
        项。
      </p>
      <div v-for="group in groups" :key="group.title">
        <h3>{{ group.title }}</h3>
        <ol class="check-list" :data-check-group="group.title">
          <li v-for="item in group.items" :key="item.no" :data-check="item.no" :data-ok="item.ok ? 'true' : 'false'">
            第 {{ item.no }} 项 · {{ item.label }} —— {{ item.ok ? '通过' : '未通过' }}
          </li>
        </ol>
      </div>
    </section>

    <section>
      <h2>验证码时机与延迟提交说明</h2>
      <ul class="check-list">
        <li>
          验证码块初始不显示；<strong>首次登录失败后显示并强制</strong>（策略
          <code>required=true</code> 时初始显示），后端返回 <code>20101</code> 亦触发。
        </li>
        <li>
          件族以 <code>submit-mode="defer"</code> 接入：件层只渲染与采集、<strong>不发校验请求</strong>，凭证经
          <code>credential</code> 事件上抛，随登录请求一次性提交（登录在请求内校验并消费挑战）。
        </li>
        <li>
          该行为由 <code>packages/ui-ep/tests/captcha-defer.spec.ts</code> 与
          <code>tests/login-view.spec.ts</code> 锁定。
        </li>
      </ul>
    </section>

    <section>
      <h2>登录接线口径</h2>
      <ul class="check-list">
        <li>
          登录经 <code>api/identity.ts::login()</code> 服务段寻址；成功后
          <code>stores/session.ts::signIn</code> 写入会话，并按核心 <code>resolveSafeRedirect</code> 回跳（非法 /
          缺失回首页）。
        </li>
        <li>
          错误码文案取核心 <code>domain/auth-error.ts</code>（验证码子段回落 <code>CAPTCHA_ERROR_TEXTS</code>），PC /
          移动端共用。
        </li>
        <li>
          SSO 入口按 <code>GET /auth/sso/providers</code> 渲染，点击经顶层地址跳转授权端点；清单为空即整块不渲染。
        </li>
        <li>密码不回填、不落存储，明文切换仅内存态；<strong>不提供「记住我」与密码强度提示</strong>。</li>
        <li>
          表单件复用组件库：租户 / 账号走 <code>TextInput</code>、密码走 <code>PasswordInput</code>（<code>:strength="false"</code>
          关闭强度条 + 明文切换图标复用 Element Plus <code>show-password</code>），按钮走 Element Plus
          <code>el-button</code>；宿主入口（<code>main.ts</code>）全量引入 Element Plus 样式，主题由令牌
          <code>--el-*</code> 映射接管。
        </li>
      </ul>
    </section>

    <section class="check-host">
      <h2>被核对页面（真实挂载）</h2>
      <div ref="host" data-test="login-host">
        <login-view />
      </div>
    </section>
  </main>
</template>

<style scoped>
.check-page {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-lg);
  padding: var(--bms-spacing-lg);
  font-family: var(--bms-font-family);
}

.check-page section {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md);
}

.check-list {
  margin: 0;
  padding-left: var(--bms-spacing-lg);
}

.check-list [data-ok='false'] {
  color: var(--bms-color-danger);
}

.check-list [data-ok='true'] {
  color: var(--bms-color-success);
}

.check-host {
  border-top: 1px dashed var(--bms-color-border);
  padding-top: var(--bms-spacing-lg);
}
</style>
