<script setup lang="ts">
// 表单框架（布局族）：列表 Tab（固定不可关）+ 记录 Tab（新增 / 双击打开、可关）容器。
// 状态**受控**（`modelValue` 激活键 + `tabs` 清单）；脏数据拦截由宿主经 `beforeClose` 回调注入。
import { computed } from 'vue'

import { useBaseLayout } from '../../composables/useBaseLayout'

/** 表单框架页签。 */
export interface FormFrameTab {
  /** 页签键（唯一）。 */
  key: string
  /** 页签标题。 */
  title: string
  /** 页签类型（列表页签 / 记录页签）。 */
  type: 'list' | 'record'
  /** 是否可关闭（记录页签缺省可关、列表页签缺省不可关）。 */
  closable?: boolean
  /** 是否存在未保存变更（标题前显示脏标记）。 */
  dirty?: boolean
}

interface Props {
  /** 当前激活页签键。 */
  modelValue: string
  /** 页签清单（插入序）。 */
  tabs: FormFrameTab[]
  /** 「新增」按钮文案（空串隐藏该按钮）。 */
  openText?: string
  /** 关闭拦截回调（返回 false 即取消关闭）；缺省不拦截。 */
  beforeClose?: (key: string) => boolean | Promise<boolean>
}

const props = withDefaults(defineProps<Props>(), { openText: '新增', beforeClose: undefined })

const emit = defineEmits<{
  'update:modelValue': [key: string]
  activate: [key: string]
  close: [key: string]
  open: []
}>()

/** 布局基类投影（显隐口径与布局族一致）。 */
const { hidden } = useBaseLayout()

/** 当前激活页签（无匹配为空）。 */
const activeTab = computed(() => props.tabs.find((tab) => tab.key === props.modelValue))

/**
 * 页签是否可关闭（列表页签缺省不可关）。
 *
 * @param tab 页签。
 */
function isClosable(tab: FormFrameTab): boolean {
  return tab.closable ?? tab.type === 'record'
}

/**
 * 激活页签。
 *
 * @param key 页签键。
 */
function onActivate(key: string): void {
  if (key === props.modelValue) {
    return
  }
  emit('update:modelValue', key)
  emit('activate', key)
}

/**
 * 关闭页签（经 `beforeClose` 拦截，返回 false 即取消）。
 *
 * @param key 页签键。
 */
async function onClose(key: string): Promise<void> {
  if (props.beforeClose !== undefined) {
    const allowed = await props.beforeClose(key)
    if (!allowed) {
      return
    }
  }
  emit('close', key)
}
</script>

<template>
  <div v-show="!hidden" class="bms-form-frame" data-test="form-frame">
    <div class="bms-form-frame__bar" role="tablist">
      <div
        v-for="tab in tabs"
        :key="tab.key"
        class="bms-form-frame__tab"
        :class="{ 'is-active': tab.key === modelValue }"
        role="tab"
        :aria-selected="tab.key === modelValue"
        :data-test="`form-frame-tab-${tab.key}`"
        @click="onActivate(tab.key)"
      >
        <span v-if="tab.dirty" class="bms-form-frame__dirty" :data-test="`form-frame-dirty-${tab.key}`">●</span>
        <span class="bms-form-frame__title">{{ tab.title }}</span>
        <button
          v-if="isClosable(tab)"
          class="bms-form-frame__close"
          :data-test="`form-frame-close-${tab.key}`"
          @click.stop="onClose(tab.key)"
        >
          ×
        </button>
      </div>
      <div class="bms-form-frame__tail">
        <slot name="extra" />
        <button v-if="openText" class="bms-form-frame__open" data-test="form-frame-open" @click="emit('open')">
          {{ openText }}
        </button>
      </div>
    </div>

    <div class="bms-form-frame__body" :data-test="`form-frame-body-${modelValue}`">
      <slot v-if="activeTab?.type === 'list'" name="list" :tab="activeTab" />
      <slot v-else name="record" :tab="activeTab" />
    </div>
  </div>
</template>

<style scoped>
.bms-form-frame {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  height: 100%;
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.bms-form-frame__bar {
  display: flex;
  flex: none;
  align-items: stretch;
  box-sizing: border-box;
  min-width: 0;
  overflow-x: auto;
  background: var(--bms-color-fill);
  border-bottom: 1px solid var(--bms-color-border);
}

.bms-form-frame__tab {
  display: inline-flex;
  flex: 0 1 auto;
  align-items: center;
  gap: var(--bms-space-2);
  min-width: 88px;
  max-width: 220px;
  height: 36px;
  padding: 0 var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
  cursor: pointer;
  user-select: none;
  border-right: 1px solid var(--bms-color-border);
  border-bottom: 2px solid transparent;
}

.bms-form-frame__tab:hover {
  color: var(--bms-color-text);
  background: var(--bms-color-bg);
}

.bms-form-frame__tab.is-active {
  color: var(--bms-color-primary);
  background: var(--bms-color-bg);
  border-bottom-color: var(--bms-color-primary);
}

.bms-form-frame__title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.bms-form-frame__dirty {
  flex: none;
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-danger);
}

.bms-form-frame__close {
  display: inline-flex;
  flex: none;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  padding: 0;
  line-height: 1;
  color: inherit;
  cursor: pointer;
  background: transparent;
  border: none;
  border-radius: var(--bms-radius-sm);
}

.bms-form-frame__close:hover {
  color: var(--bms-color-white);
  background: var(--bms-color-text-secondary);
}

.bms-form-frame__tail {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: var(--bms-space-2);
  margin-left: auto;
  padding: 0 var(--bms-space-2);
  border-left: 1px solid var(--bms-color-border);
}

.bms-form-frame__open {
  height: 28px;
  padding: 0 var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-primary);
  cursor: pointer;
  background: transparent;
  border: 1px dashed var(--bms-color-primary);
  border-radius: var(--bms-radius-sm);
}

.bms-form-frame__open:hover {
  background: var(--bms-color-bg);
}

.bms-form-frame__body {
  flex: 1;
  min-height: 0;
  padding: var(--bms-space-4);
  overflow: auto;
}
</style>
