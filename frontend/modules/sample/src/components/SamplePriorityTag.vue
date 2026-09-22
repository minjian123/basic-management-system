<script setup lang="ts">
// 优先级标签：复用平台状态标签件 + 模块语义色映射与模块文案（不重复造件、不硬编码色值）。
import { StatusTag } from '@bms/ui-ep'
import { computed } from 'vue'

import { useSampleI18n } from '../composables/useSampleI18n'
import { SAMPLE_PRIORITIES, SAMPLE_PRIORITY_SEMANTIC, labelKeyOf, type SamplePriority } from '../domain'

/** 属性。 */
interface Props {
  /** 优先级取值。 */
  value: SamplePriority
}

const props = defineProps<Props>()
const { t } = useSampleI18n()

const text = computed(() => t(labelKeyOf(SAMPLE_PRIORITIES, props.value)))
const semantic = computed(() => SAMPLE_PRIORITY_SEMANTIC[props.value])
</script>

<template>
  <status-tag shape="light" :value="value" :text="text" :semantic="semantic" data-test="sample-priority-tag" />
</template>
