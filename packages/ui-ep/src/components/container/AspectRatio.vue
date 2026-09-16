<script setup lang="ts">
/**
 * 宽高比容器（《组件设计 · 宽高比容器》）：固定宽高比、占位防抖动。
 *
 * - 比例：`ratio`（数字或 `'w/h'`；非法回退 `16/9` + 开发态告警）——主路径 CSS `aspect-ratio`，
 *   `@supports not (aspect-ratio: 1 / 1)` 降级 padding-top 技巧（经 `--bms-aspect-ratio-number` 计算）；
 * - `fit`：作用于内容层媒体元素（`img` / `video` / `iframe` / `canvas` → `object-fit`）；
 *   样式变量 `--bms-aspect-ratio-fit` 可覆盖；普通内容默认铺满；
 * - `maxWidth` / `minHeight` 限制；占位默认背景块（令牌），`#placeholder` 可自定义。
 */

import { computed, useAttrs } from 'vue'

import { useComponentBase } from '@bms/vue'

import { resolveSize } from './size'

const props = withDefaults(
  defineProps<{
    /** 宽高比（数字或 `'w/h'`；非法回退 `16/9`） */
    ratio?: number | string
    /** 内容填充（映射 `object-fit`） */
    fit?: 'fill' | 'contain' | 'cover' | 'none'
    /** 最大宽度（数字按 px） */
    maxWidth?: number | string
    /** 最小高度（px） */
    minHeight?: number
  }>(),
  {
    ratio: '16/9',
    fit: 'cover',
    maxWidth: undefined,
    minHeight: undefined,
  },
)

const base = useComponentBase({ ns: 'bms', identifier: 'aspect-ratio' })
const attrs = useAttrs()

interface ParsedRatio {
  value: number
  css: string
}

function parseRatio(input: number | string): ParsedRatio {
  if (typeof input === 'number') {
    if (Number.isFinite(input) && input > 0) {
      return { value: input, css: String(input) }
    }
  } else {
    const text = input.trim()
    const match = /^(\d+(?:\.\d+)?)\s*[/:]\s*(\d+(?:\.\d+)?)$/.exec(text)
    if (match) {
      const width = Number(match[1])
      const height = Number(match[2])
      if (width > 0 && height > 0) {
        return { value: width / height, css: `${match[1]} / ${match[2]}` }
      }
    }
    const plain = Number(text)
    if (Number.isFinite(plain) && plain > 0) {
      return { value: plain, css: String(plain) }
    }
  }
  if (import.meta.env.DEV) {
    console.warn(`[AspectRatio] 非法 ratio：${String(input)}（回退 16/9）`)
  }
  return { value: 16 / 9, css: '16 / 9' }
}

const parsed = computed(() => parseRatio(props.ratio))

const elAttrs = computed(() => {
  const { class: cls, style: sty, ...rest } = base.passthroughAttrs(attrs as Record<string, unknown>)
  return base.rootAttrs({
    class: [
      base.nsClass('aspect-ratio'),
      base.nsClass(`aspect-ratio--fit-${props.fit}`),
      cls,
    ],
    style: sty,
    ...rest,
  })
})

const rootStyle = computed<Record<string, string>>(() => {
  const style: Record<string, string> = {
    '--bms-aspect-ratio-number': String(parsed.value.value),
    '--bms-aspect-ratio-fit': props.fit,
    'aspect-ratio': parsed.value.css,
  }
  const maxWidth = resolveSize(props.maxWidth)
  if (maxWidth) {
    style.maxWidth = maxWidth
  }
  if (props.minHeight !== undefined) {
    style.minHeight = `${props.minHeight}px`
  }
  return style
})
</script>

<template>
  <div v-bind="elAttrs" :class="base.nsClass('aspect-ratio')" :style="rootStyle">
    <div :class="base.nsClass('aspect-ratio-placeholder')" data-testid="aspect-placeholder">
      <slot name="placeholder" />
    </div>
    <div :class="base.nsClass('aspect-ratio-content')">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.bms-aspect-ratio {
  position: relative;
  width: 100%;
  overflow: hidden;
  border-radius: var(--bms-radius-sm);
}

.bms-aspect-ratio-placeholder {
  width: 100%;
  height: 100%;
  background: var(--bms-color-bg-page);
}

.bms-aspect-ratio-content {
  position: absolute;
  inset: 0;
}

.bms-aspect-ratio-content :is(img, video, iframe, canvas) {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: var(--bms-aspect-ratio-fit, cover);
}

/* 旧浏览器降级：padding-top 技巧（内容层绝对定位已就位） */
@supports not (aspect-ratio: 1 / 1) {
  .bms-aspect-ratio {
    aspect-ratio: auto;
    height: auto;
  }

  .bms-aspect-ratio::before {
    content: '';
    display: block;
    padding-top: calc(100% / var(--bms-aspect-ratio-number, 1.7778));
  }
}
</style>
