<script setup lang="ts">
// 系统信息面板（展示类）：记录页「系统信息」子页签通用件——ID / 版本号 / 审计四字段 / 表单标识。
// 口径同《布局设计 · 表单页》§2.1.1 与《布局设计 · 字典页》§2.5：label 置于字段上方、三列只读栅格；
// 第 7 项为表单标识（禁用下拉框：显示表单名、值为 form_key）；时间按租户时区格式化为
// `yyyy-MM-dd HH:mm`（不加时区后缀），无法解析的值原样输出；缺失值以占位符呈现。
import { ElCol, ElForm, ElFormItem, ElInput, ElOption, ElRow, ElSelect } from 'element-plus'
import { computed, watch } from 'vue'

import { useBaseDisplay } from '../../composables/useBaseDisplay'

/** 系统信息数据（字段可空，缺失以占位符呈现）。 */
export interface SysInfoData {
  /** 实体主键。 */
  id?: string | number | null
  /** 乐观锁版本。 */
  version?: number | null
  /** 创建人。 */
  createdBy?: string | number | null
  /** 创建时间（UTC）。 */
  createdAt?: string | null
  /** 更新人。 */
  updatedBy?: string | number | null
  /** 更新时间（UTC）。 */
  updatedAt?: string | null
  /** 表单标识（第 7 项：界面显示表单名、值为该标识）。 */
  formKey?: string | null
  /** 表单名称。 */
  formLabel?: string | null
}

/** 陈列项（文本项 / 表单标识项；顺序固定）。 */
interface SysInfoItem {
  /** 项标签。 */
  label: string
  /** 文本项展示值（表单标识项为 `undefined`）。 */
  text?: string
  /** 表单标识项：禁用下拉框的显示名与值。 */
  select?: { label: string; value: string }
}

interface Props {
  /** 系统信息数据。 */
  info: SysInfoData
  /** 面板标题（空串不渲染标题）。 */
  title?: string
  /** 每行列数（缺省 3，与布局设计的「三列等宽」一致）。 */
  column?: number
  /** 空值占位符。 */
  placeholder?: string
  /** 时间格式化时区（按租户时区传入即符合布局设计口径）。 */
  timezone?: string
}

const props = withDefaults(defineProps<Props>(), {
  title: '系统信息',
  column: 3,
  placeholder: '—',
  timezone: 'Asia/Shanghai',
})

/** 展示基类投影（值随 `info` 进入展示状态：空值语义归基类判定）。 */
const { value: displayValue, setValue } = useBaseDisplay<SysInfoData>()

watch(() => props.info, (next) => setValue(next), { immediate: true, deep: true })

/** 栅格跨度（三列等宽口径；非法列数回落三列）。 */
const span = computed(() => Math.floor(24 / Math.max(1, props.column)))

/**
 * 展示值（空值回落占位符）。
 *
 * @param value 原始值。
 * @returns 展示文本。
 */
function display(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') {
    return props.placeholder
  }
  return String(value)
}

/**
 * 格式化时间为 `yyyy-MM-dd HH:mm`（按传入时区、无时区后缀）。
 *
 * @param value 时间值（ISO 串 / 时间戳；已格式化文本同样可解析）。
 * @returns 格式化结果；不可解析（含非法时区）返回 `undefined`。
 */
function formatMinute(value: string | number | null | undefined): string | undefined {
  if (value === null || value === undefined || value === '') {
    return undefined
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return undefined
  }
  try {
    const parts = new Intl.DateTimeFormat('zh-CN', {
      timeZone: props.timezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hourCycle: 'h23',
    }).formatToParts(date)
    const read = (type: string): string => parts.find((part) => part.type === type)?.value ?? ''
    return `${read('year')}-${read('month')}-${read('day')} ${read('hour')}:${read('minute')}`
  } catch {
    return undefined
  }
}

/**
 * 时间项展示值（可解析则按租户时区格式化，否则原样输出，最终空值回落占位符）。
 *
 * @param value 时间值。
 * @returns 展示文本。
 */
function displayTime(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') {
    return props.placeholder
  }
  return formatMinute(value) ?? String(value)
}

/** 陈列项（固定 7 项与顺序：ID / 版本号 / 创建用户 / 创建时间 / 修改用户 / 修改时间 / 表单标识）。 */
const items = computed<SysInfoItem[]>(() => {
  const info = displayValue.value ?? {}
  const formKey = info.formKey ?? ''
  const rows: SysInfoItem[] = [
    { label: 'ID', text: display(info.id) },
    { label: '版本号', text: display(info.version) },
    { label: '创建用户', text: display(info.createdBy) },
    { label: '创建时间', text: displayTime(info.createdAt) },
    { label: '修改用户', text: display(info.updatedBy) },
    { label: '修改时间', text: displayTime(info.updatedAt) },
  ]
  if (formKey === '') {
    rows.push({ label: '表单标识', text: props.placeholder })
  } else {
    rows.push({ label: '表单标识', select: { label: info.formLabel ?? formKey, value: formKey } })
  }
  return rows
})
</script>

<template>
  <div class="bms-sys-info" data-test="sys-info-panel">
    <h4 v-if="title" class="bms-sys-info__title">{{ title }}</h4>
    <el-form label-position="top" class="bms-sys-info__form">
      <el-row :gutter="16">
        <el-col v-for="item in items" :key="item.label" :span="span">
          <el-form-item :label="item.label">
            <el-select
              v-if="item.select"
              class="bms-sys-info__field"
              :model-value="item.select.value"
              disabled
              :data-test="`sys-info-${item.label}`"
            >
              <el-option :label="item.select.label" :value="item.select.value" />
            </el-select>
            <el-input
              v-else
              class="bms-sys-info__field"
              :model-value="item.text"
              disabled
              :data-test="`sys-info-${item.label}`"
            />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
  </div>
</template>

<style scoped>
.bms-sys-info__title {
  margin: 0 0 var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  font-weight: 600;
  color: var(--bms-color-text);
}

.bms-sys-info__form {
  padding: var(--bms-space-1) 0 var(--bms-space-4);
}
</style>
