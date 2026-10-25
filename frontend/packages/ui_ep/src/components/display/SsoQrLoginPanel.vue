<!-- 扫码登录面板（05_04）：经二维码件渲染授权二维码 + 四态展示 + 多源切换 + 过期 / 失败 / 确认事件。
     轮询 / 退避 / 过期 / 可见性编排落本面板（经 useBaseSsoQr 投影核心能力 `BaseSsoQr`），二维码件保持纯展示。
     数据通路经注入式状态源（未注入即占位零请求）；真实平台适配归阶段十七。 -->
<script setup lang="ts">
import {
  selectScannableProviders,
  SSO_QR_BACK_TEXT,
  SSO_QR_EMPTY_TEXT,
  SSO_QR_FAILED_TEXT,
  SSO_QR_REFRESH_TEXT,
  SSO_QR_TITLE_TEXT,
  type SsoQrLoginSourceAdapter,
  type SsoQrPhase,
  type SsoQrProviderLike,
} from '@bms/core'
import { ElButton } from 'element-plus'
import { computed, onBeforeUnmount, onMounted, watch } from 'vue'

import { useBaseSsoQr } from '../../composables/useBaseSsoQr'
import { onVisibilityChange } from '../../utils/visibility'
import QrCode, { type QrStatus } from './QrCode.vue'

/** 面板可扫码入口（在最小结构上补名称 / 图标，与 SSO 入口清单兼容）。 */
export interface SsoQrPanelProvider extends SsoQrProviderLike {
  /** 展示名称。 */
  name?: string
  /** 图标地址。 */
  icon?: string
}

interface Props {
  /** 可扫码入口（原始清单；面板内过滤 + 排序）。 */
  providers?: readonly SsoQrPanelProvider[]
  /** 当前 IdP 标识（可选受控）。 */
  activeIdpKey?: string | null
  /** 状态源（未注入即占位零请求）。 */
  source?: SsoQrLoginSourceAdapter
  /** 数据通路是否就绪（缺省 true）。 */
  ready?: boolean
  /** 轮询间隔基数（毫秒）。 */
  pollInterval?: number
  /** 轮询退避上限（毫秒）。 */
  backoffMax?: number
  /** 连续失败阈值。 */
  maxFailures?: number
  /** 页面隐藏时是否暂停轮询。 */
  pauseWhenHidden?: boolean
  /** 标题。 */
  title?: string
  /** 提示追加。 */
  tips?: string
}

const props = withDefaults(defineProps<Props>(), {
  providers: () => [],
  activeIdpKey: null,
  source: undefined,
  ready: true,
  pollInterval: 2000,
  backoffMax: 30_000,
  maxFailures: 5,
  pauseWhenHidden: true,
  title: SSO_QR_TITLE_TEXT,
  tips: '',
})

const emit = defineEmits<{
  confirmed: [payload: { redirect?: string }]
  expired: []
  failed: [payload: { reason: string; failures: number }]
  switch: [idpKey: string]
  refresh: []
  back: []
}>()

/** 相位 → 二维码件状态映射。 */
const QR_STATUS_MAP: Record<SsoQrPhase, QrStatus> = {
  pending: 'active',
  scanned: 'scanning',
  confirmed: 'confirmed',
  expired: 'expired',
  failed: 'failed',
}

const {
  instance,
  phase,
  statusText,
  authorizeUrl,
  activeIdpKey,
  remaining,
  empty,
  terminal,
  setProviders,
  setActiveProvider,
  setSource,
  setReady,
  setOptions,
  init,
  refresh,
  pause,
  resume,
} = useBaseSsoQr({
  ready: props.ready,
  providers: props.providers,
  source: props.source,
  pollBase: props.pollInterval,
  pollMax: props.backoffMax,
  maxFailures: props.maxFailures,
  pauseWhenHidden: props.pauseWhenHidden,
})

/** 可扫码入口（保留名称 / 图标，供切换控件渲染）。 */
const list = computed<SsoQrPanelProvider[]>(() => selectScannableProviders(props.providers))

watch(
  () => props.providers,
  (next) => {
    setProviders(next)
    void init()
  },
)
watch(
  () => props.source,
  (next) => setSource(next),
)
watch(
  () => props.ready,
  (next) => {
    setReady(next)
    if (next) {
      void init()
    }
  },
)
watch(
  () => [props.pollInterval, props.backoffMax, props.maxFailures, props.pauseWhenHidden],
  () =>
    setOptions({
      pollBase: props.pollInterval,
      pollMax: props.backoffMax,
      maxFailures: props.maxFailures,
      pauseWhenHidden: props.pauseWhenHidden,
    }),
)

/** 相位变化上抛（确认 / 过期 / 失败）。 */
watch(phase, (next) => {
  if (next === 'confirmed') {
    const redirect = instance.redirect
    emit('confirmed', redirect === undefined ? {} : { redirect })
  } else if (next === 'expired') {
    emit('expired')
  } else if (next === 'failed') {
    emit('failed', { reason: 'poll-failed', failures: instance.failures })
  }
})

/** 可见性变化：暂停 / 恢复轮询（经 `utils/visibility` 单一落点，组件不直触浏览器能力）。 */
let offVisibility: (() => void) | undefined

/** 切换入口。 */
function onSwitch(provider: SsoQrPanelProvider): void {
  if (provider.idp_key === activeIdpKey.value) {
    return
  }
  setActiveProvider(provider.idp_key)
  emit('switch', provider.idp_key)
  void init()
}

/** 刷新（含二维码件过期遮罩的刷新）。 */
function onRefresh(): void {
  refresh()
  emit('refresh')
}

onMounted(() => {
  void init()
  if (props.pauseWhenHidden) {
    offVisibility = onVisibilityChange((visible) => {
      if (visible) {
        resume()
      } else {
        pause()
      }
    })
  }
})
onBeforeUnmount(() => {
  offVisibility?.()
  offVisibility = undefined
})
</script>

<template>
  <div class="bms-sso-qr-panel" data-test="sso-qr-panel" :data-phase="phase">
    <slot name="header">
      <p class="bms-sso-qr-panel__title">{{ title }}</p>
    </slot>

    <template v-if="!empty">
      <div v-if="list.length > 1" class="bms-sso-qr-panel__switch" data-test="sso-qr-switch">
        <el-button
          v-for="provider in list"
          :key="provider.idp_key"
          size="small"
          :type="provider.idp_key === activeIdpKey ? 'primary' : 'default'"
          :data-test="`sso-qr-switch-${provider.idp_key}`"
          @click="onSwitch(provider)"
        >
          {{ provider.name ?? provider.idp_key }}
        </el-button>
      </div>

      <div class="bms-sso-qr-panel__code">
        <qr-code
          v-if="authorizeUrl !== ''"
          :value="authorizeUrl"
          :status="QR_STATUS_MAP[phase]"
          :expires-in="remaining"
          :downloadable="false"
          :copyable="false"
          @refresh="onRefresh"
        />
        <div v-else class="bms-sso-qr-panel__loading" data-test="sso-qr-loading">二维码生成中…</div>
        <p class="bms-sso-qr-panel__tip" data-test="sso-qr-tip">{{ statusText }}</p>
        <p v-if="tips !== ''" class="bms-sso-qr-panel__hint">{{ tips }}</p>
        <slot name="tip" />
      </div>

      <p v-if="phase === 'failed'" class="bms-sso-qr-panel__error" role="alert" data-test="sso-qr-error">
        {{ SSO_QR_FAILED_TEXT }}
      </p>

      <div class="bms-sso-qr-panel__actions">
        <el-button v-if="terminal" data-test="sso-qr-refresh" @click="onRefresh">
          {{ SSO_QR_REFRESH_TEXT }}
        </el-button>
        <el-button data-test="sso-qr-back" @click="emit('back')">{{ SSO_QR_BACK_TEXT }}</el-button>
      </div>
    </template>

    <template v-else>
      <slot name="empty">
        <p class="bms-sso-qr-panel__empty" data-test="sso-qr-empty">{{ SSO_QR_EMPTY_TEXT }}</p>
        <div class="bms-sso-qr-panel__actions">
          <el-button data-test="sso-qr-back" @click="emit('back')">{{ SSO_QR_BACK_TEXT }}</el-button>
        </div>
      </slot>
    </template>

    <slot name="footer" />
  </div>
</template>

<style scoped>
.bms-sso-qr-panel {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md);
}

.bms-sso-qr-panel__title {
  margin: 0;
  font-size: 14px;
  color: var(--bms-color-text);
}

.bms-sso-qr-panel__switch {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm);
  justify-content: center;
}

.bms-sso-qr-panel__code {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
  align-items: center;
}

.bms-sso-qr-panel__loading {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 160px;
  height: 160px;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
  border: 1px dashed var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-sso-qr-panel__tip {
  margin: 0;
  font-size: 13px;
  color: var(--bms-color-text-secondary);
}

.bms-sso-qr-panel__hint {
  margin: 0;
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}

.bms-sso-qr-panel__error {
  margin: 0;
  font-size: 12px;
  color: var(--bms-color-danger);
}

.bms-sso-qr-panel__empty {
  margin: 0;
  font-size: 13px;
  color: var(--bms-color-text-secondary);
}

.bms-sso-qr-panel__actions {
  display: flex;
  gap: var(--bms-spacing-sm);
  justify-content: center;
}
</style>
