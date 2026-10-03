<script setup lang="ts">
// 区域件：用户扩展信息「扩展示例明细」Tab（只读；区域项声明 `perm` 按权限显隐，无写权限即不渲染）。
import { DescriptionList, SectionContainer } from '@bms/ui-ep'
import type { DescItem } from '@bms/ui-ep'
import { computed, onMounted, ref } from 'vue'

import { useSlotSampleI18n } from '../composables/useSlotSampleI18n'
import { currentEntityId, slotSampleRuntime } from '../runtime'
import { listUserExtensions, type UserExtensionItem } from '../services/user-extension-service'

defineOptions({ name: 'SlotExtensionDetailTab' })

const { t } = useSlotSampleI18n()
const runtime = slotSampleRuntime()

const rows = ref<UserExtensionItem[]>([])
const loading = ref(false)
const errorText = ref('')

/** 宿主页作用实体标识（空串即未选择用户，不发起请求）。 */
const entityId = computed(() => currentEntityId())
const hasEntity = computed(() => entityId.value !== '')

/** 明细字段（逐行只读呈现）。 */
const items: DescItem[] = [
  { key: 'label', label: t('slotSample.column.label') },
  { key: 'remark', label: t('slotSample.column.remark'), crossColumn: true },
]

/** 加载明细（未选择用户时不请求）。 */
async function load(): Promise<void> {
  if (!hasEntity.value) {
    rows.value = []
    return
  }
  loading.value = true
  errorText.value = ''
  try {
    rows.value = await listUserExtensions(entityId.value)
  } catch (caught) {
    rows.value = []
    errorText.value = String(caught)
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <section-container :title="t('slotSample.detail.title')">
    <p class="slot-sample__runtime" data-test="slot-extension-permission-count">
      {{ runtime.permissionCount }}
    </p>
    <p v-if="!hasEntity" class="slot-sample__hint" data-test="slot-extension-detail-no-entity">
      {{ t('slotSample.hint.noEntity') }}
    </p>
    <p v-if="errorText !== ''" class="slot-sample__hint" data-test="slot-extension-detail-error">
      {{ errorText }}
    </p>
    <p v-if="loading" class="slot-sample__hint">{{ t('slotSample.detail.title') }}</p>
    <description-list
      v-for="item in rows"
      :key="item.id"
      :items="items"
      :data="{ label: item.label, remark: item.remark ?? '' }"
      :columns="2"
      plain-enabled
    />
    <p v-if="!loading && errorText === '' && rows.length === 0" class="slot-sample__hint">
      {{ t('slotSample.detail.empty') }}
    </p>
  </section-container>
</template>

<style scoped>
.slot-sample__hint {
  margin: 0 0 var(--bms-spacing-sm, 4px);
  color: var(--bms-color-text-secondary);
}

.slot-sample__runtime {
  margin: 0 0 var(--bms-spacing-sm, 4px);
  color: var(--bms-color-text-secondary);
}
</style>
