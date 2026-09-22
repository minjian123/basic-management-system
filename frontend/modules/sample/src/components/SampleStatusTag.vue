<script setup lang="ts">
// 状态标签：复用平台状态标签件 + 模块语义色映射与模块文案。
import { StatusTag } from '@bms/ui-ep'
import { computed } from 'vue'

import { useSampleI18n } from '../composables/useSampleI18n'
import { SAMPLE_STATUSES, SAMPLE_STATUS_SEMANTIC, labelKeyOf, type SampleStatus } from '../domain'

/** 属性。 */
interface Props {
  /** 状态取值。 */
  value: SampleStatus
}

const props = defineProps<Props>()
const { t } = useSampleI18n()

const text = computed(() => t(labelKeyOf(SAMPLE_STATUSES, props.value)))
const semantic = computed(() => SAMPLE_STATUS_SEMANTIC[props.value])
</script>

<template>
  <status-tag shape="light" :value="value" :text="text" :semantic="semantic" data-test="sample-status-tag" />
</template>
