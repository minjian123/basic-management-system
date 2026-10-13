<script setup lang="ts">
// 开发态核对页（08_01 字典页布局对齐）：字典记录页骨架件（工具栏 + 详细信息 / 系统信息两 Tab +
// 详细信息首行三字段 Code / Name / State）与通用系统信息件的真实组装，作为《原型审查规范》
// 实现侧截图对照载体（数据为本地样例，不调后端）；本页不进构建产物。
import { DictRecordLayout, SysInfoPanel, type SysInfoData } from '@bms/ui-ep'
import { computed, ref } from 'vue'

/** 当前子页签。 */
const section = ref('detail')
/** 是否编辑态（只读 / 编辑分态）。 */
const editing = ref(false)
/** 样例系统信息（时间为 UTC，按租户时区呈现）。 */
const sysInfo: SysInfoData = {
  id: '802553432413044736',
  version: 3,
  createdBy: '1001',
  createdAt: '2026-10-06T01:30:00Z',
  updatedBy: '1002',
  updatedAt: '2026-10-07T03:20:00Z',
  formKey: 'role',
  formLabel: '角色管理',
}
/** 详细信息是否只读（骨架 `disabled` 绑定，对齐「只读 / 编辑分态」）。 */
const readOnly = computed(() => !editing.value)
</script>

<template>
  <div class="dict-check" data-test="dict-record-check">
    <div class="dict-check__bar">
      <strong>开发态核对 · 字典记录页骨架与系统信息件（08_01）</strong>
      <span class="dict-check__hint" data-test="check-state">
        激活子页签：{{ section }}·{{ editing ? '编辑态' : '只读态' }}
      </span>
    </div>

    <div class="dict-check__body">
      <dict-record-layout v-model="section" :info="sysInfo" :disabled="readOnly" data-test="check-dict-layout">
        <template #toolbar>
          <el-button v-if="!editing" type="primary" @click="editing = true">修改</el-button>
          <template v-else>
            <el-button type="primary">保存</el-button>
            <el-button @click="editing = false">撤销</el-button>
          </template>
          <el-button>刷新</el-button>
          <el-button>关闭</el-button>
        </template>

        <template #first-row>
          <el-col :span="8">
            <el-form-item label="角色码" required>
              <el-input model-value="ops_admin" placeholder="角色码（租户内唯一）" data-test="check-code" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="角色名" required>
              <el-input model-value="运维管理员" data-test="check-name" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="状态">
              <el-select model-value="enabled" data-test="check-state-select">
                <el-option label="启用" value="enabled" />
                <el-option label="停用" value="disabled" />
              </el-select>
            </el-form-item>
          </el-col>
        </template>

        <template #fields>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="角色类型">
                <el-input model-value="自定义" disabled />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <template #extra-tabs>
          <el-tab-pane label="权限配置" name="permission">
            <p class="dict-check__hint">业务 Tab 不受限：本页示例为「权限配置」，与详细信息、系统信息并列。</p>
          </el-tab-pane>
        </template>
      </dict-record-layout>
    </div>

    <div class="dict-check__bar">
      <strong>对照件 · 系统信息（仅本件）</strong>
      <span class="dict-check__hint">对照《原型设计 · 公共原型 04 系统信息组件》</span>
    </div>
    <div class="dict-check__body">
      <sys-info-panel :info="sysInfo" data-test="check-sys-info" />
    </div>
  </div>
</template>

<style scoped>
.dict-check {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--bms-space-4);
  background: var(--bms-color-bg-page);
}

.dict-check__bar {
  display: flex;
  flex: none;
  gap: 12px;
  align-items: center;
  padding-bottom: var(--bms-space-3);
}

.dict-check__hint {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.dict-check__body {
  flex: none;
  margin-bottom: var(--bms-space-4);
  padding: var(--bms-space-4);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}
</style>
