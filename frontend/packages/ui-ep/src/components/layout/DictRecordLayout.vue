<script setup lang="ts">
// 字典记录页骨架（布局族）：所有字典（基础数据）记录页共用的记录页模板——
// 工具栏 + 信息栏「详细信息 / 系统信息」两个子页签（最少两 Tab）；详细信息首行固定为三个字典系统字段
// （字段标识 Code / Name / State，三列等宽、顺序固定，由 `first-row` 插槽填入），其后为其余字段
// （`fields` 插槽）与业务 Tab（`extra-tabs` 插槽，不受限）；系统信息由通用系统信息件承载。
// 口径见《布局设计 · 字典页》§2：字典记录页据此一次对齐，后续新增字典记录页直接套用本骨架。
import { ElForm, ElRow, ElTabPane, ElTabs } from 'element-plus'
import { computed } from 'vue'

import SysInfoPanel, { type SysInfoData } from '../display/SysInfoPanel.vue'
import { useBaseLayout } from '../../composables/useBaseLayout'

interface Props {
  /** 激活子页签（受控；`detail` / `sys` 或业务 Tab 名）。 */
  modelValue: string
  /** 系统信息数据（传内置系统信息件）。 */
  info: SysInfoData
  /** 详细信息是否只读（绑定详情区表单）。 */
  disabled?: boolean
  /** 时间格式化时区（传内置系统信息件；缺省按件内缺省时区）。 */
  timezone?: string
  /** 详细信息页签文案。 */
  detailLabel?: string
  /** 系统信息页签文案。 */
  sysLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  disabled: false,
  timezone: undefined,
  detailLabel: '详细信息',
  sysLabel: '系统信息',
})

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()

const { hidden } = useBaseLayout()

/** 激活页签（受控读写）。 */
const active = computed({
  get: () => props.modelValue,
  set: (value: string) => emit('update:modelValue', value),
})
</script>

<template>
  <div v-show="!hidden" class="bms-dict-record" data-test="dict-record-layout">
    <div class="bms-dict-record__toolbar">
      <slot name="toolbar" />
    </div>
    <el-tabs v-model="active" class="bms-dict-record__tabs" data-test="dict-record-tabs">
      <el-tab-pane :label="detailLabel" name="detail">
        <el-form class="bms-dict-record__form" label-position="top" :disabled="disabled">
          <el-row :gutter="16">
            <slot name="first-row" />
          </el-row>
          <slot name="fields" />
        </el-form>
      </el-tab-pane>
      <slot name="extra-tabs" />
      <el-tab-pane :label="sysLabel" name="sys">
        <sys-info-panel :info="info" :timezone="timezone" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.bms-dict-record {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  min-height: 0;
}

.bms-dict-record__toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}
</style>
