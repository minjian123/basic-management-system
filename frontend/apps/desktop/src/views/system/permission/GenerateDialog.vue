<script setup lang="ts">
// 批量补生成缺失权限码组合对话框：范围（全部 / 指定业务 / 指定动作）+ 是否含停用项。
// 原型未覆盖该交互（《03_03_02 详细设计》决策 5），已在原型迭代记录登记为增强项。
defineOptions({ name: 'GenerateDialog' })

import { ElMessage } from 'element-plus'
import { computed, ref, watch } from 'vue'

import type { ActionItem } from '@/api/action'
import type { BusinessItem } from '@/api/business'
import type { PermissionGeneratePayload } from '@/api/permission'

const props = defineProps<{
  /** 是否可见（`v-model`）。 */
  modelValue: boolean
  /** 业务码清单。 */
  businesses: BusinessItem[]
  /** 动作码清单。 */
  actions: ActionItem[]
}>()

const emit = defineEmits<{
  /** 可见性变更。 */
  'update:modelValue': [visible: boolean]
  /** 提交补生成请求。 */
  submit: [payload: PermissionGeneratePayload]
}>()

/** 生成范围。 */
type Scope = 'all' | 'business' | 'action'

/** 范围选择。 */
const scope = ref<Scope>('all')
/** 指定业务码。 */
const businessIds = ref<string[]>([])
/** 指定动作码。 */
const actionIds = ref<string[]>([])
/** 是否包含停用项。 */
const includeDisabled = ref(false)

// 每次打开重置为缺省范围（全部启用项）
watch(
  () => props.modelValue,
  (visible) => {
    if (visible) {
      scope.value = 'all'
      businessIds.value = []
      actionIds.value = []
      includeDisabled.value = false
    }
  },
)

/** 业务码选项（停用项标注）。 */
const businessOptions = computed(() =>
  props.businesses.map((item) => ({
    value: item.id,
    label: `${item.code}${item.status === 'enabled' ? '' : '（停用）'}`,
  })),
)

/** 动作码选项（停用项标注）。 */
const actionOptions = computed(() =>
  props.actions.map((item) => ({
    value: item.id,
    label: `${item.code}${item.status === 'enabled' ? '' : '（停用）'}`,
  })),
)

/**
 * 关闭对话框。
 */
function close(): void {
  emit('update:modelValue', false)
}

/**
 * 确认（按范围组装请求；指定范围必须至少选一项）。
 */
function confirm(): void {
  if (scope.value === 'business' && businessIds.value.length === 0) {
    ElMessage.error('请选择业务码')
    return
  }
  if (scope.value === 'action' && actionIds.value.length === 0) {
    ElMessage.error('请选择动作码')
    return
  }
  emit('submit', {
    business_ids: scope.value === 'business' ? [...businessIds.value] : [],
    action_ids: scope.value === 'action' ? [...actionIds.value] : [],
    include_disabled: includeDisabled.value,
  })
  close()
}
</script>

<template>
  <el-dialog
    :model-value="props.modelValue"
    title="补生成缺失组合"
    width="560px"
    :close-on-click-modal="false"
    data-test="generate-dialog"
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
  >
    <div class="generate-dialog__body">
      <p class="generate-dialog__hint">
        按「业务码 × 动作码」补齐缺失的权限码组合；已存在的组合会跳过（软删除行恢复），不覆盖既有授权。
      </p>
      <el-form label-position="top">
        <el-form-item label="生成范围">
          <el-radio-group v-model="scope" data-test="generate-scope">
            <el-radio value="all">全部（启用业务 × 启用动作）</el-radio>
            <el-radio value="business">指定业务码</el-radio>
            <el-radio value="action">指定动作码</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="scope === 'business'" label="业务码" required>
          <el-select v-model="businessIds" multiple filterable collapse-tags style="width: 100%" data-test="generate-businesses">
            <el-option v-for="item in businessOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="scope === 'action'" label="动作码" required>
          <el-select v-model="actionIds" multiple filterable collapse-tags style="width: 100%" data-test="generate-actions">
            <el-option v-for="item in actionOptions" :key="item.value" :label="item.label" :value="item.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="包含停用项">
          <el-switch v-model="includeDisabled" active-text="是" inactive-text="否" data-test="generate-include-disabled" />
          <div class="generate-dialog__hint">用于数据修复：范围含停用的业务 / 动作码时一并补齐</div>
        </el-form-item>
      </el-form>
    </div>
    <template #footer>
      <el-button data-test="generate-cancel" @click="close">取消</el-button>
      <el-button type="primary" data-test="generate-confirm" @click="confirm">确定</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.generate-dialog__body {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-2);
}

.generate-dialog__hint {
  margin: 0;
  font-size: var(--bms-font-size-xs);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text-secondary);
}
</style>
