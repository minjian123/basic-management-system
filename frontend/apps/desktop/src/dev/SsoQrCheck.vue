<script setup lang="ts">
// 开发态核对页（05_04 扫码登录前端）：四组自检程序化跑一遍并上屏；本页不进构建产物。
import {
  isScannableIdpType,
  isSsoQrTerminal,
  nextSsoQrPollDelay,
  normalizeSsoQrAuthorizeInfo,
  normalizeSsoQrPollResult,
  resolveSsoQrStatusText,
  selectScannableProviders,
  SSO_QR_MAX_FAILURES,
  SSO_QR_POLL_BASE,
  SSO_QR_POLL_MAX,
  type SsoQrPhase,
} from '@bms/core'
import { computed } from 'vue'

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

/** 可扫码源过滤结果。 */
const scannable = selectScannableProviders([
  { idp_key: 'w2', type: 'wecom', sort: 20 },
  { idp_key: 'o1', type: 'oidc', sort: 1 },
  { idp_key: 'd1', type: 'dingtalk', sort: 10 },
])

/** 退避序列。 */
const backoff = [1, 2, 3, 4, 5, 9].map((attempt) => nextSsoQrPollDelay(attempt))

/** 归一结果快照。 */
const info = normalizeSsoQrAuthorizeInfo({ authorize_url: 'https://idp', state: 's', expires_in: 30 })
const pollUnknown = normalizeSsoQrPollResult({ status: 'weird' })
const pollConfirmed = normalizeSsoQrPollResult({ status: 'confirmed', redirect: '/home' })
const pollBadRedirect = normalizeSsoQrPollResult({ status: 'confirmed', redirect: '' })

/** 相位文案（逐相位非空）。 */
const phases: SsoQrPhase[] = ['pending', 'scanned', 'confirmed', 'expired', 'failed']
const textNonEmpty = phases.every((phase) => resolveSsoQrStatusText(phase).length > 0)

/** 自检分组清单。 */
const groups = computed<CheckGroup[]>(() => {
  let no = 0
  const next = (label: string, ok: boolean): CheckItem => {
    no += 1
    return { no, label, ok }
  }
  return [
    {
      title: '一、可扫码身份源',
      items: [
        next('wecom / dingtalk 判定为可扫码，oidc / cas 不可扫码', isScannableIdpType('wecom') && isScannableIdpType('dingtalk') && !isScannableIdpType('oidc') && !isScannableIdpType('cas')),
        next(
          `过滤非可扫码项并按 sort 升序（实得 ${scannable.map((item) => item.idp_key).join(' → ')}）`,
          scannable.length === 2 && scannable[0]?.idp_key === 'd1' && scannable[1]?.idp_key === 'w2',
        ),
      ],
    },
    {
      title: '二、退避与终态',
      items: [
        next(
          `指数退避 2s / 4s / 8s / 16s / 30s 且封顶（实得 ${backoff.join(' / ')}）`,
          backoff[0] === SSO_QR_POLL_BASE &&
            backoff[1] === 4000 &&
            backoff[2] === 8000 &&
            backoff[3] === 16000 &&
            backoff[4] === SSO_QR_POLL_MAX &&
            backoff[5] === SSO_QR_POLL_MAX,
        ),
        next(`连续失败阈值 ${SSO_QR_MAX_FAILURES}`, SSO_QR_MAX_FAILURES === 5),
        next(
          '终态判定：confirmed / expired / failed 为终态，pending / scanned 否',
          isSsoQrTerminal('confirmed') && isSsoQrTerminal('expired') && isSsoQrTerminal('failed') && !isSsoQrTerminal('pending') && !isSsoQrTerminal('scanned'),
        ),
      ],
    },
    {
      title: '三、契约归一',
      items: [
        next(
          `authorize-url 归一（${info.authorizeUrl} / ${info.state} / ${info.expiresIn}s）`,
          info.authorizeUrl === 'https://idp' && info.state === 's' && info.expiresIn === 30,
        ),
        next('未知轮询状态回落 pending', pollUnknown.status === 'pending'),
        next('confirmed 透出 redirect', pollConfirmed.status === 'confirmed' && pollConfirmed.redirect === '/home'),
        next('空 redirect 丢弃', pollBadRedirect.status === 'confirmed' && pollBadRedirect.redirect === undefined),
      ],
    },
    {
      title: '四、相位文案',
      items: [next('五相位文案均非空', textNonEmpty)],
    },
  ]
})

/** 全部自检项。 */
const items = computed(() => groups.value.flatMap((group) => group.items))

/** 通过项数。 */
const passed = computed(() => items.value.filter((item) => item.ok).length)
</script>

<template>
  <main class="check-page">
    <h1>扫码登录核对页（05_04 扫码登录前端）</h1>

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
          <li
            v-for="item in group.items"
            :key="item.no"
            :data-check="item.no"
            :data-ok="item.ok ? 'true' : 'false'"
          >
            第 {{ item.no }} 项 · {{ item.label }} —— {{ item.ok ? '通过' : '未通过' }}
          </li>
        </ol>
      </div>
    </section>

    <section>
      <h2>状态源与占位口径</h2>
      <ul class="check-list">
        <li>状态源落核心 <code>capabilities/sso-qr-source</code>（<code>BaseSsoQrSource</code> + <code>SsoQrSourceRegistry</code>）；宿主内建实现真实取授权 URL。</li>
        <li>后端无扫码状态端点、平台不暴露「已扫」态：宿主 <code>poll</code> 占位恒 <code>pending</code>（零请求、零副作用）；四态流转由可注入状态源 / 测试夹具覆盖。</li>
        <li>真实平台适配（企微 <code>@wecom/jssdk</code> / 钉钉内嵌登录或后端状态端点）归阶段十七，届时仅替换状态源实现。</li>
      </ul>
    </section>

    <section>
      <h2>状态机与体验口径</h2>
      <ul class="check-list">
        <li>四态：待扫 <code>pending</code> / 已扫待确认 <code>scanned</code>（可注入，平台不暴露）/ 已确认 <code>confirmed</code> / 过期 <code>expired</code>；另加失败 <code>failed</code>。</li>
        <li>轮询 2s 起、指数退避至 30s；页面隐藏暂停；到期停轮询并自动重取一次。</li>
        <li>确认后：带 <code>redirect</code> 顶层跳转，否则会话就绪（<code>ensureReady</code>）+ 站内安全回跳。</li>
      </ul>
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
</style>
