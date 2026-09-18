<script setup lang="ts">
// 间距分割线：`el-divider` 薄封装 + 间距档位（令牌）。
import { ElDivider } from 'element-plus'
import { computed, type CSSProperties } from 'vue'

/** 间距档位。 */
export type SpacingSize = 'sm' | 'md' | 'lg'

const SPACING: Record<SpacingSize, string> = { sm: '8px', md: '16px', lg: '24px' }

interface Props {
  /** 方向。 */
  direction?: 'horizontal' | 'vertical'
  /** 文案位置。 */
  position?: 'left' | 'center' | 'right'
  /** 间距档位。 */
  size?: SpacingSize
  /** 虚线。 */
  dashed?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  direction: 'horizontal',
  position: 'center',
  size: 'md',
  dashed: false,
})

const style = computed<CSSProperties>(() =>
  props.direction === 'horizontal' ? { marginBlock: SPACING[props.size] } : { marginInline: SPACING[props.size] },
)
</script>

<template>
  <el-divider
    class="bms-spacing-divider"
    :style="style"
    :direction="direction"
    :content-position="position"
    :border-style="dashed ? 'dashed' : 'solid'"
  >
    <slot />
  </el-divider>
</template>
