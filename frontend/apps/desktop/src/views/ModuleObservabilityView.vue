<script setup lang="ts">
// 开发态模块观测面板（dev-only 路由，不进生产构建）：按模块查看加载 / 渲染耗时、错误与 Web Vitals。
// 体积按模块可见由发布记录 size 字段与 CI（module-build）汇总承载，本页不读文件系统。
import { computed, ref } from 'vue'

import { getModuleLoader } from '@/module/host'
import { moduleSnapshot, resetModuleTelemetry } from '@/observability'

interface ModuleRow {
  name: string
  version: string
  mode: string
  enabled: boolean
  mounted: boolean
  resolveMs: number | null
  setupMs: number | null
  mountMs: number | null
  renderMs: number | null
  errorCount: number
}

const snapshot = ref(moduleSnapshot())

const rows = computed<ModuleRow[]>(() => {
  const loader = getModuleLoader()
  const names = loader?.names() ?? []
  return names.map((name) => {
    const entry = loader?.entryOf(name)
    const grouped = snapshot.value.modules[name]
    const load = grouped?.load ?? []
    const lastOk = (phase: string) => {
      const found = [...load].reverse().find((item) => item.phase === phase)
      return found?.durationMs ?? null
    }
    return {
      name,
      version: entry?.version ?? grouped?.version ?? '',
      mode: entry?.mode ?? '',
      enabled: entry?.enabled ?? true,
      mounted: loader?.isMounted(name) ?? false,
      resolveMs: lastOk('resolve'),
      setupMs: lastOk('setup'),
      mountMs: lastOk('mount'),
      renderMs: lastOk('render'),
      errorCount: grouped?.errors.length ?? 0,
    }
  })
})

const errors = computed(() => {
  const collected: { module: string; version: string; phase: string; message: string; at: string }[] = []
  for (const [name, grouped] of Object.entries(snapshot.value.modules)) {
    for (const item of grouped.errors) {
      collected.push({ module: name, version: item.version, phase: item.phase, message: item.message, at: item.at })
    }
  }
  for (const item of snapshot.value.platform.errors) {
    collected.push({ module: 'platform', version: item.version, phase: item.phase, message: item.message, at: item.at })
  }
  return collected.reverse()
})

const vitals = computed(() => {
  const collected: { scope: string; metric: string; value: number; rating: string; at: string }[] = []
  for (const [name, grouped] of Object.entries(snapshot.value.modules)) {
    for (const item of grouped.vitals) {
      collected.push({ scope: name, metric: item.metric, value: item.value, rating: item.rating, at: item.at })
    }
  }
  for (const item of snapshot.value.platform.vitals) {
    collected.push({ scope: 'platform', metric: item.metric, value: item.value, rating: item.rating, at: item.at })
  }
  return collected.reverse()
})

function refresh(): void {
  snapshot.value = moduleSnapshot()
}

function clear(): void {
  resetModuleTelemetry()
  refresh()
}

function ms(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(0)} ms`
}
</script>

<template>
  <section class="module-observability">
    <header class="module-observability__header">
      <h2>模块观测（开发态）</h2>
      <div>
        <el-button size="small" @click="refresh">刷新</el-button>
        <el-button size="small" @click="clear">清空记录</el-button>
      </div>
    </header>

    <h3>模块与耗时</h3>
    <el-table :data="rows" size="small" data-test="observability-modules">
      <el-table-column prop="name" label="模块" />
      <el-table-column prop="version" label="版本" width="90" />
      <el-table-column prop="mode" label="形态" width="80" />
      <el-table-column label="可见" width="70">
        <template #default="{ row }">{{ row.enabled ? '是' : '停用' }}</template>
      </el-table-column>
      <el-table-column label="已挂载" width="80">
        <template #default="{ row }">{{ row.mounted ? '是' : '否' }}</template>
      </el-table-column>
      <el-table-column label="resolve" width="90">
        <template #default="{ row }">{{ ms(row.resolveMs) }}</template>
      </el-table-column>
      <el-table-column label="setup" width="90">
        <template #default="{ row }">{{ ms(row.setupMs) }}</template>
      </el-table-column>
      <el-table-column label="mount" width="90">
        <template #default="{ row }">{{ ms(row.mountMs) }}</template>
      </el-table-column>
      <el-table-column label="渲染" width="90">
        <template #default="{ row }">{{ ms(row.renderMs) }}</template>
      </el-table-column>
      <el-table-column prop="errorCount" label="错误数" width="80" />
    </el-table>
    <p class="module-observability__hint">体积按模块可见见发布记录 size 字段与 CI module-build 汇总输出。</p>

    <h3>错误（按模块）</h3>
    <el-table :data="errors" size="small" data-test="observability-errors">
      <el-table-column prop="module" label="模块" width="120" />
      <el-table-column prop="version" label="版本" width="90" />
      <el-table-column prop="phase" label="阶段" width="90" />
      <el-table-column prop="message" label="原因" />
      <el-table-column prop="at" label="时间" width="200" />
    </el-table>

    <h3>Web Vitals（按模块）</h3>
    <el-table :data="vitals" size="small" data-test="observability-vitals">
      <el-table-column prop="scope" label="归属" width="120" />
      <el-table-column prop="metric" label="指标" width="90" />
      <el-table-column prop="value" label="值" width="100" />
      <el-table-column prop="rating" label="评级" width="140" />
      <el-table-column prop="at" label="时间" width="200" />
    </el-table>
  </section>
</template>

<style scoped>
.module-observability {
  padding: var(--bms-space-4, 16px);
}

.module-observability__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.module-observability__hint {
  color: var(--bms-color-text-secondary, inherit);
  font-size: var(--bms-font-size-sm, 12px);
}
</style>
