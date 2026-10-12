<script setup lang="ts">
// 开发态核对页（03_01 弹窗抽屉表单）：表单抽屉 / 表单对话框 / 确认对话框三件**真实组装**——三态
// （新增 / 编辑 / 查看）、尺寸阶梯、脏数据拦截、关闭规则（遮罩 / Esc / 提交中禁关）、危险语义与
// 页脚动作，作为《原型审查规范》§4.9「实现 ↔ 原型」的截图与行为核对载体；本页不进构建产物。
import { ConfirmDialog, FormDialog, FormDrawer } from '@bms/ui-ep'
import { ElButton, ElInput, ElOption, ElSelect, ElSwitch } from 'element-plus'
import { computed, ref } from 'vue'

/** 表单三态。 */
type FormMode = 'create' | 'edit' | 'detail'
/** 抽屉尺寸阶梯。 */
type DrawerSize = 'sm' | 'md' | 'lg' | 'xl'
/** 对话框尺寸阶梯。 */
type DialogSize = 'sm' | 'md' | 'lg'

/** 当前三态。 */
const mode = ref<FormMode>('create')
/** 抽屉尺寸档位。 */
const drawerSize = ref<DrawerSize>('md')
/** 对话框尺寸档位。 */
const dialogSize = ref<DialogSize>('sm')
/** 脏数据（为真时关闭需确认）。 */
const dirty = ref(false)
/** 提交加载态（为真时禁止任何方式关闭）。 */
const loading = ref(false)
/** 表单字段（演示脏数据）。 */
const fieldValue = ref('示例值')

/** 抽屉显隐。 */
const drawerVisible = ref(false)
/** 对话框显隐。 */
const dialogVisible = ref(false)
/** 确认对话框显隐。 */
const confirmVisible = ref(false)
/** 确认对话框危险语义。 */
const confirmDanger = ref(true)
/** 操作日志（末 8 条）。 */
const events = ref<string[]>([])

/** 三态标题（缺省由件按对象名组合）。 */
const modeLabel = computed(() => ({ create: '新增部门', edit: '编辑部门', detail: '部门详情' })[mode.value])

/**
 * 记一条操作日志。
 *
 * @param text 日志文本。
 */
function record(text: string): void {
  events.value = [...events.value.slice(-7), text]
}

/**
 * 打开抽屉（指定三态）。
 *
 * @param next 目标三态。
 */
function openDrawer(next: FormMode): void {
  mode.value = next
  drawerVisible.value = true
  record(`抽屉打开：${next}`)
}

/**
 * 打开表单对话框（指定三态）。
 *
 * @param next 目标三态。
 */
function openDialog(next: FormMode): void {
  mode.value = next
  dialogVisible.value = true
  record(`对话框打开：${next}`)
}

/**
 * 打开确认对话框。
 *
 * @param danger 是否危险语义。
 */
function openConfirm(danger: boolean): void {
  confirmDanger.value = danger
  confirmVisible.value = true
  record(`确认对话框打开：${danger ? '危险' : '常规'}`)
}

/** 模拟提交中（2 秒后复位）。 */
function simulateSubmitting(): void {
  loading.value = true
  record('进入提交中（2s）')
  window.setTimeout(() => {
    loading.value = false
    record('提交中结束')
  }, 2000)
}
</script>

<template>
  <div class="mc-page">
    <header class="mc-head">
      <h1>开发态核对 · 弹窗抽屉表单（03_01）</h1>
      <p class="mc-sub">
        三件真实组装：表单抽屉 <code>FormDrawer</code> / 表单对话框 <code>FormDialog</code> / 确认对话框
        <code>ConfirmDialog</code>——核对三态、尺寸阶梯、脏数据拦截、关闭规则（遮罩 / Esc / 提交中禁关）与危险语义。
      </p>
    </header>

    <section class="mc-bar" data-check="controls">
      <span class="mc-label">三态</span>
      <el-button size="small" data-test="mc-open-create" @click="openDrawer('create')">抽屉 · 新增</el-button>
      <el-button size="small" data-test="mc-open-edit" @click="openDrawer('edit')">抽屉 · 编辑</el-button>
      <el-button size="small" data-test="mc-open-detail" @click="openDrawer('detail')">抽屉 · 查看</el-button>
      <span class="mc-label">抽屉尺寸</span>
      <el-select v-model="drawerSize" size="small" style="width: 96px" data-test="mc-drawer-size">
        <el-option v-for="item in ['sm', 'md', 'lg', 'xl']" :key="item" :label="item" :value="item" />
      </el-select>
      <el-button size="small" data-test="mc-open-dialog-create" @click="openDialog('create')">对话框 · 新增</el-button>
      <el-button size="small" data-test="mc-open-dialog-detail" @click="openDialog('detail')">对话框 · 详情</el-button>
      <span class="mc-label">对话框尺寸</span>
      <el-select v-model="dialogSize" size="small" style="width: 88px" data-test="mc-dialog-size">
        <el-option v-for="item in ['sm', 'md', 'lg']" :key="item" :label="item" :value="item" />
      </el-select>
    </section>

    <section class="mc-bar" data-check="close-rules">
      <span class="mc-label">脏数据</span>
      <el-switch v-model="dirty" data-test="mc-dirty" />
      <span class="mc-label">提交中</span>
      <el-switch v-model="loading" data-test="mc-loading" />
      <el-button size="small" data-test="mc-submitting" @click="simulateSubmitting">模拟提交中（2s）</el-button>
      <el-button size="small" data-test="mc-open-confirm-danger" @click="openConfirm(true)">确认 · 危险（删除）</el-button>
      <el-button size="small" data-test="mc-open-confirm-plain" @click="openConfirm(false)">确认 · 常规</el-button>
    </section>

    <section class="mc-grid">
      <div class="mc-card">
        <b>① 表单抽屉三态与尺寸</b>
        <span>轻量表单首选；宽度走阶梯 400 / 480 / 640 / 720，标题「动作 + 对象」。</span>
      </div>
      <div class="mc-card">
        <b>② 对话框与确认</b>
        <span>简单表单（≤ 4 字段）走对话框 420 / 480 / 520；确认类危险语义、禁遮罩与 Esc。</span>
      </div>
      <div class="mc-card">
        <b>③ 关闭规则</b>
        <span>表单类禁点遮罩关闭；Esc 与取消走脏数据拦截；提交中禁止任何方式关闭。</span>
      </div>
      <div class="mc-card">
        <b>④ 事件</b>
        <span>提交 / 取消 / 关闭 / 确认回调均落日志，核对交互闭环。</span>
      </div>
    </section>

    <section class="mc-state">
      <div class="mc-state-line">
        三态=<code>{{ mode }}</code>（{{ modeLabel }}）；抽屉尺寸=<code>{{ drawerSize }}</code>；对话框尺寸=<code>{{ dialogSize }}</code>；
        脏数据=<code>{{ dirty }}</code>；提交中=<code>{{ loading }}</code>
      </div>
      <div class="mc-log" data-check="log">{{ events.length === 0 ? '等待操作…' : events.join(' ｜ ') }}</div>
    </section>

    <!-- 三件真实组装（件内为插槽内容；仅演示，不改组件实现） -->
    <form-drawer
      v-model="drawerVisible"
      :mode="mode"
      :size="drawerSize"
      :dirty="dirty"
      :loading="loading"
      object-name="部门"
      @submit="record('抽屉提交')"
      @cancel="record('抽屉取消')"
      @closed="record('抽屉已关闭')"
    >
      <div class="mc-field">
        <span class="mc-field-label">部门名称</span>
        <el-input v-model="fieldValue" size="small" data-test="mc-field" />
      </div>
      <div class="mc-field">
        <span class="mc-field-label">说明</span>
        <el-input
          v-model="fieldValue"
          type="textarea"
          :rows="3"
          size="small"
          placeholder="轻量表单内容由调用方插槽提供；件内不内联业务字段。"
        />
      </div>
    </form-drawer>

    <form-dialog
      v-model="dialogVisible"
      :mode="mode"
      :size="dialogSize"
      :dirty="dirty"
      :loading="loading"
      object-name="部门"
      @submit="record('对话框提交')"
      @cancel="record('对话框取消')"
      @closed="record('对话框已关闭')"
    >
      <div class="mc-field">
        <span class="mc-field-label">部门名称</span>
        <el-input v-model="fieldValue" size="small" data-test="mc-dialog-field" />
      </div>
    </form-dialog>

    <confirm-dialog
      v-model="confirmVisible"
      :title="confirmDanger ? '删除部门' : '重置密码'"
      :content="confirmDanger ? '删除后不可恢复，确定删除该部门吗？' : '将为该用户重置为初始密码，确定继续吗？'"
      :danger="confirmDanger"
      :confirm-text="confirmDanger ? '删除' : '确定'"
      @confirm="record('确认回调')"
      @cancel="record('确认取消')"
    />
  </div>
</template>

<style scoped>
.mc-page {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-lg);
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--bms-spacing-lg);
  background: var(--bms-color-bg);
  color: var(--bms-color-text);
}

.mc-head h1 {
  margin: 0 0 var(--bms-spacing-xs);
  font-size: 18px;
}

.mc-sub {
  margin: 0;
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.mc-bar {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
  flex-wrap: wrap;
  padding: var(--bms-spacing-sm) var(--bms-spacing-md);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  background: var(--bms-color-fill);
}

.mc-label {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.mc-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: var(--bms-spacing-md);
}

.mc-card {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-xs);
  padding: var(--bms-spacing-md);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.mc-card span,
.mc-state-line {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.mc-state {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-xs);
}

.mc-log {
  padding: var(--bms-spacing-sm);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  background: var(--bms-color-fill);
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.mc-field {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-xs);
  margin-bottom: var(--bms-spacing-md);
}

.mc-field-label {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}
</style>
