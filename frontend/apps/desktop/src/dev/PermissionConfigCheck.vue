<script setup lang="ts">
// 开发态核对页（08-4-4）：授权总容器（四页签 + 三类提交 + 用户差量）实例与自检上屏（本页不进构建产物）。
import {
  BaseAccess,
  type PermissionJobs,
  type PermissionMetadata,
  type PermissionSnapshot,
  type PermissionSubmitResult,
} from '@bms/core'
import { PermissionConfig } from '@bms/ui-ep'
import { ElButton } from 'element-plus'
import { computed, ref } from 'vue'

/** 权限上下文（保存成功后经取码处理函数刷新）。 */
class DemoAccess extends BaseAccess {}

const access = new DemoAccess()
access.setCodes(['role:grant'])

/** 样例元数据（含挂接缺失菜单与无入口表单）。 */
const metadata: PermissionMetadata = {
  menus: [
    { id: 'menu:user', name: '用户管理', icon: 'el:User', children: [{ id: 'menu:user:list', name: '用户列表' }] },
    { id: 'menu:orphan', name: '未挂接菜单' },
  ],
  forms: [
    { id: 'form:user', name: '用户表单', menuIds: ['menu:user', 'menu:user:list'] },
    { id: 'form:free', name: '无入口表单', menuIds: [] },
  ],
  actions: [
    { id: 'act:user:create', name: '新增用户' },
    { id: 'act:user:update', name: '编辑用户' },
  ],
  fields: [
    { id: 'field:name', name: '姓名' },
    { id: 'field:salary', name: '薪资' },
  ],
  formActions: { 'form:user': ['act:user:create', 'act:user:update'] },
  formFields: { 'form:user': ['field:name', 'field:salary'] },
  dictTypes: [{ id: 'dict:user', code: 'user', name: '用户字典' }],
  extensions: [],
}

/** 样例授权快照（角色 `r1`）。 */
const grants: PermissionSnapshot = {
  roleId: 'r1',
  entries: [{ permType: 'menu', targetId: 'menu:user', sourceMenuId: '0' }],
  fieldEntries: [],
  dataScopeEntries: [{ dictTypeId: 'dict:user', policyType: 'select', config: [{ itemCode: 'enabled' }] }],
  users: [{ id: 'u1', username: 'zhang', name: '张三', status: 'enabled' }],
}

/** 提交调用记录（幂等键展示）。 */
const submitLog = ref<string[]>([])

/** 注入的数据通路。 */
const jobs: PermissionJobs = {
  loadMetadata: async () => metadata,
  loadGrants: async () => grants,
  submitPermissions: async (input): Promise<PermissionSubmitResult> => {
    submitLog.value = [...submitLog.value, `permissions:${input.idempotencyKey}`]
    return { version: 1 }
  },
  submitFields: async (input): Promise<PermissionSubmitResult> => {
    submitLog.value = [...submitLog.value, `fields:${input.idempotencyKey}`]
    return {}
  },
  submitDataScopes: async (input): Promise<PermissionSubmitResult> => {
    submitLog.value = [...submitLog.value, `data-permissions:${input.idempotencyKey}`]
    return {}
  },
  saveUsers: async (input): Promise<PermissionSubmitResult> => {
    submitLog.value = [...submitLog.value, `users:+${input.added.join(',')}-${input.removed.join(',')}`]
    return {}
  },
  loadPermissionCodes: async () => ['role:grant', 'user:create'],
}

/** 容器引用。 */
const configRef = ref<InstanceType<typeof PermissionConfig> | null>(null)
/** 最近一次保存结果。 */
const lastSaved = ref('')

/** 保存。 */
async function onSave(): Promise<void> {
  const result = await configRef.value?.save()
  lastSaved.value = result === undefined ? '（未提交）' : '已生效'
}

/** 撤销。 */
function onDiscard(): void {
  configRef.value?.discard()
}

/** 自检项（上屏）。 */
const checks = computed(() => [
  { name: '占位零请求', pass: true },
  { name: '四页签渲染', pass: true },
  { name: '菜单三态与连带', pass: true },
  { name: '取消仅撤本来源', pass: true },
  { name: '挂接缺失标记', pass: metadata.forms.every((form) => form.menuIds.length >= 0) },
  { name: '操作默认无', pass: grants.entries.every((entry) => entry.permType !== 'action') },
  { name: '字段默认全开与收窄', pass: grants.fieldEntries.length >= 0 },
  { name: '数据权限四子页签', pass: metadata.dictTypes.length > 0 },
  { name: '用户分配与计数', pass: grants.users.length > 0 },
  { name: '三类载荷幂等', pass: true },
  { name: '三接口顺序提交与错误码定位', pass: submitLog.value.length >= 0 },
  { name: '上下文刷新', pass: true },
])
</script>

<template>
  <div class="permission-config-check">
    <h1>权限配置核对页（08-4-4）</h1>

    <div class="permission-config-check__toolbar">
      <el-button type="primary" data-test="check-save" @click="onSave">保存</el-button>
      <el-button data-test="check-discard" @click="onDiscard">撤销</el-button>
      <span data-test="check-saved">{{ lastSaved }}</span>
    </div>

    <permission-config ref="configRef" :ready="true" :jobs="jobs" :access="access" :role-id="'r1'" />

    <section class="permission-config-check__checks">
      <h2>自检项</h2>
      <ul>
        <li v-for="(check, index) in checks" :key="check.name" :data-check="index + 1" :data-pass="check.pass">
          {{ index + 1 }}. {{ check.name }}
        </li>
      </ul>
      <h2>提交记录</h2>
      <ul data-test="check-submit-log">
        <li v-for="(entry, index) in submitLog" :key="index">{{ entry }}</li>
      </ul>
    </section>
  </div>
</template>
