<script setup lang="ts">
// 语言清单件（08_07）：code / name / rtl / status 增改启停与删除；默认语言与「至少一种启用语言」保护；新增与编辑走弹窗表单。
import type { I18nLocaleInput, I18nLocaleItem } from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseMessageCatalog } from '../../composables/useBaseMessageCatalog'
import { useConfirm } from '../../composables/useConfirm'
import SwitchField from '../field/SwitchField.vue'
import FormDialog from '../modal/FormDialog.vue'

interface Props {
  /** 语言清单。 */
  locales: readonly I18nLocaleItem[]
  /** 默认语言（不可停用 / 删除）。 */
  defaultLocale?: string
  /** 禁用（占位 / 无权）。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  defaultLocale: 'zh-CN',
  disabled: false,
})

const emit = defineEmits<{
  add: [input: I18nLocaleInput]
  update: [payload: { code: string; patch: I18nLocaleInput }]
  toggle: [payload: { code: string; enabled: boolean }]
  remove: [code: string]
}>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
const { catalog } = useBaseMessageCatalog()
const { confirm } = useConfirm()

/** 弹窗显隐。 */
const dialogVisible = ref(false)
/** 弹窗模式（新增 / 编辑）。 */
const dialogMode = ref<'create' | 'edit'>('create')
/** 弹窗表单（code / name / rtl）。 */
const form = ref<{ code: string; name: string; rtl: boolean }>({ code: '', name: '', rtl: false })
/** 弹窗内联错误文案。 */
const formError = ref('')

/** 启用语言数（至少一种保护）。 */
const enabledCount = computed(() => props.locales.filter((item) => item.status === 'enabled').length)

/**
 * 是否禁用停用按钮（默认语言或仅剩一种启用语言）。
 *
 * @param item 语言项。
 */
function toggleDisabled(item: I18nLocaleItem): boolean {
  if (props.disabled) {
    return true
  }
  return item.status === 'enabled' && (item.code === props.defaultLocale || enabledCount.value <= 1)
}

/**
 * 是否禁用删除按钮（默认语言）。
 *
 * @param item 语言项。
 */
function removeDisabled(item: I18nLocaleItem): boolean {
  return props.disabled || item.code === props.defaultLocale
}

/** 打开新增弹窗。 */
function openAdd(): void {
  dialogMode.value = 'create'
  form.value = { code: '', name: '', rtl: false }
  formError.value = ''
  dialogVisible.value = true
}

/**
 * 打开编辑弹窗。
 *
 * @param item 语言项。
 */
function openEdit(item: I18nLocaleItem): void {
  dialogMode.value = 'edit'
  form.value = { code: item.code, name: item.name, rtl: item.rtl }
  formError.value = ''
  dialogVisible.value = true
}

/** 提交弹窗表单（弹窗 `submit` 事件驱动）。 */
function submitForm(): void {
  const code = form.value.code.trim()
  if (code === '') {
    formError.value = '语言标识不可为空'
    return
  }
  if (dialogMode.value === 'create') {
    emit('add', { code, name: form.value.name.trim(), rtl: form.value.rtl, status: 'enabled' })
  } else {
    emit('update', { code, patch: { code, name: form.value.name.trim(), rtl: form.value.rtl } })
  }
  dialogVisible.value = false
}

/**
 * 切换启停（受控：只上抛，回退态由父件经清单下发）。
 *
 * @param item 语言项。
 */
function onToggle(item: I18nLocaleItem): void {
  emit('toggle', { code: item.code, enabled: item.status !== 'enabled' })
}

/**
 * 删除语言（二次确认）。
 *
 * @param item 语言项。
 */
async function onRemove(item: I18nLocaleItem): Promise<void> {
  const accepted = await confirm({ content: `确认删除语言「${item.name}」？存在语言包数据时将不可删除。`, danger: true })
  if (accepted) {
    emit('remove', item.code)
  }
}

watch(dialogVisible, (value) => {
  if (!value) {
    formError.value = ''
  }
})
</script>

<template>
  <div class="bms-locale-list" data-test="locale-list" :data-source="catalog.identifier">
    <div class="bms-locale-list__actions">
      <button type="button" data-test="locale-add" :disabled="disabled" @click="openAdd">新增语言</button>
    </div>

    <p v-if="locales.length === 0" data-test="locale-empty">
      <slot name="empty">暂无语言</slot>
    </p>

    <table v-else class="bms-locale-list__table">
      <thead>
        <tr>
          <th>code</th>
          <th>name</th>
          <th>rtl</th>
          <th>status</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in locales" :key="item.code" :data-test="`locale-row-${item.code}`">
          <td data-test="locale-code">{{ item.code }}</td>
          <td :data-test="`locale-name-${item.code}`">{{ item.name }}</td>
          <td :data-test="`locale-rtl-${item.code}`">{{ item.rtl ? '是' : '否' }}</td>
          <td :data-test="`locale-status-${item.code}`" :data-status="item.status">
            {{ item.status === 'enabled' ? '启用' : '停用' }}
          </td>
          <td>
            <span v-if="item.code === defaultLocale" data-test="locale-default">默认</span>
            <button
              type="button"
              :data-test="`locale-toggle-${item.code}`"
              :disabled="toggleDisabled(item)"
              @click="onToggle(item)"
            >
              {{ item.status === 'enabled' ? '停用' : '启用' }}
            </button>
            <button type="button" :data-test="`locale-edit-${item.code}`" :disabled="disabled" @click="openEdit(item)">
              编辑
            </button>
            <button
              type="button"
              :data-test="`locale-remove-${item.code}`"
              :disabled="removeDisabled(item)"
              @click="onRemove(item)"
            >
              删除
            </button>
            <slot name="actions" :item="item" />
          </td>
        </tr>
      </tbody>
    </table>

    <FormDialog
      v-model="dialogVisible"
      :mode="dialogMode === 'create' ? 'create' : 'edit'"
      object-name="语言"
      size="sm"
      :dirty="form.code !== '' || form.name !== ''"
      @submit="submitForm"
    >
      <div class="bms-locale-list__form">
        <label>
          <span>code</span>
          <input
            type="text"
            data-test="locale-form-code"
            :disabled="dialogMode === 'edit'"
            :value="form.code"
            @input="form.code = ($event.target as HTMLInputElement).value"
          />
        </label>
        <label>
          <span>name</span>
          <input
            type="text"
            data-test="locale-form-name"
            :value="form.name"
            @input="form.name = ($event.target as HTMLInputElement).value"
          />
        </label>
        <SwitchField v-model="form.rtl" data-test="locale-form-rtl" />
        <p v-if="formError !== ''" data-test="locale-form-error">{{ formError }}</p>
      </div>
    </FormDialog>
  </div>
</template>

<style scoped>
.bms-locale-list__table {
  width: 100%;
  border-collapse: collapse;
}

.bms-locale-list__table th,
.bms-locale-list__table td {
  border: 1px solid var(--bms-color-border);
  padding: 4px 8px;
  text-align: left;
}

.bms-locale-list__form {
  display: grid;
  gap: 8px;
}
</style>
