import { fileURLToPath, URL } from 'node:url'

import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

import { loadModulePackage, moduleVersionDefine } from '../../scripts/module-meta.mjs'

/** 模块工程目录（版本单一来源：`package.json`）。 */
const MODULE_DIR = fileURLToPath(new URL('.', import.meta.url))

// 版本注入与构建配置同源（缺一即测试与构建版本口径不一致）
const MODULE_VERSION = loadModulePackage(MODULE_DIR).version

export default defineConfig({
  define: moduleVersionDefine(MODULE_VERSION),
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.spec.ts'],
  },
})
