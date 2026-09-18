<script setup lang="ts">
// 卡片：`el-card` 薄封装，支持标题 / 附加区 / 页脚与标题栏折叠。
import { ElCard } from 'element-plus'
import { computed, ref, useSlots, type CSSProperties } from 'vue'

/** 内边距档位。 */
export type CardPadding = 'none' | 'sm' | 'md' | 'lg'

const PADDING: Record<CardPadding, string> = { none: '0', sm: '12px', md: '16px', lg: '24px' }

interface Props {
  /** 标题。 */
  title?: string
  /** 阴影。 */
  shadow?: 'always' | 'hover' | 'never'
  /** 内边距档位。 */
  padding?: CardPadding
  /** 标题栏可折叠。 */
  collapsible?: boolean
  /** 是否带边框。 */
  bordered?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  title: '',
  shadow: 'hover',
  padding: 'md',
  collapsible: false,
  bordered: true,
})

const slots = useSlots()
const collapsed = ref(false)
const bodyStyle = computed<CSSProperties>(() => ({ padding: PADDING[props.padding] }))
const hasHeader = computed(() => props.title !== '' || slots.header !== undefined || slots.extra !== undefined)
const bodyVisible = computed(() => !props.collapsible || !collapsed.value)

function toggle(): void {
  if (props.collapsible) {
    collapsed.value = !collapsed.value
  }
}
</script>

<template>
  <el-card class="bms-layout-card" :shadow="shadow" :body-style="bodyStyle" :class="{ 'is-bordered': bordered }">
    <template v-if="hasHeader" #header>
      <div class="bms-layout-card__header" :class="{ 'is-collapsible': collapsible }" @click="toggle">
        <span class="bms-layout-card__title">
          <slot name="header">{{ title }}</slot>
        </span>
        <span class="bms-layout-card__extra" @click.stop>
          <slot name="extra" />
        </span>
      </div>
    </template>
    <div v-show="bodyVisible" class="bms-layout-card__body">
      <slot />
    </div>
    <template v-if="$slots.footer" #footer>
      <slot name="footer" />
    </template>
  </el-card>
</template>
