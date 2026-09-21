// kiwi_id: 980
/** 护栏：模块隔离（样式作用域与令牌 / 全局污染五类 / 运行时约束；源码面与产物面双扫描，含 fixture 拦截）。 */

import { existsSync } from 'node:fs'
import { resolve } from 'node:path'

import { describe, expect, it } from 'vitest'

import {
  collectModuleSourceFiles,
  collectProductTargets,
  scanModuleProducts,
  scanProductFiles,
  scanSourceFiles,
  type IsolationFile,
} from '../../../scripts/check-module-isolation.mjs'

/** `frontend/` 目录（本文件位于 `frontend/apps/desktop/tests/`）。 */
const FRONTEND_DIR = resolve(import.meta.dirname, '../../..')

describe('模块隔离护栏（Kiwi 980）', () => {
  it('模块源码零违规（模块工程 + 宿主构建期合并模块目录）', () => {
    const files = collectModuleSourceFiles(FRONTEND_DIR)
    expect(files.length).toBeGreaterThan(0)
    expect(scanSourceFiles(files)).toEqual([])
  })

  it('全局污染五类被拦截（原型 / 事件 / 全局变量赋值 / 根节点 / 全局样式）', () => {
    const problems = scanSourceFiles([
      { path: 'a.ts', source: 'Object.prototype.polluted = true' },
      { path: 'b.ts', source: 'window.addEventListener("resize", () => {})' },
      { path: 'c.ts', source: 'window.__bms_shared = {}' },
      { path: 'd.ts', source: 'document.body.appendChild(node)' },
      { path: 'e.vue', source: '<template><div /></template>\n<style>\nbody { margin: 0; }\n</style>' },
    ])
    expect(problems.length).toBeGreaterThanOrEqual(5)
  })

  it('样式作用域与令牌消费被拦截（未 scoped / :global / 全局选择器 / 硬编码色值 / 脚本引样式）', () => {
    const problems = scanSourceFiles([
      { path: 'a.vue', source: '<style>\n.x { color: red; }\n</style>' },
      { path: 'b.vue', source: '<style scoped>\n:global(.x) { color: red; }\n</style>' },
      { path: 'c.vue', source: '<style scoped>\n* { box-sizing: border-box; }\n</style>' },
      { path: 'd.vue', source: '<style scoped>\n.x { color: #123456; }\n</style>' },
      { path: 'e.ts', source: "import './theme.scss'" },
    ])
    expect(problems.length).toBeGreaterThanOrEqual(5)
  })

  it('运行时约束被拦截（自建宿主实例 / 持久化 API）', () => {
    const problems = scanSourceFiles([
      { path: 'a.ts', source: 'const pinia = createPinia()' },
      { path: 'b.ts', source: 'const router = createRouter({ history })' },
      { path: 'c.ts', source: 'localStorage.setItem("k", "v")' },
      { path: 'd.ts', source: 'sessionStorage.getItem("k")' },
      { path: 'e.ts', source: 'const token = document.cookie' },
    ])
    expect(problems.length).toBeGreaterThanOrEqual(5)
  })

  it('豁免不误判（独立预览壳 / 令牌定义源 / 令牌消费 / :deep / 动态色值）', () => {
    const files: IsolationFile[] = [
      { path: 'src/standalone.ts', source: "import 'element-plus/dist/index.css'\ncreateApp({}).mount('#app')" },
      { path: 'src/tokens.scss', source: ':root { --bms-color-primary: #3a7bd5; }' },
      {
        path: 'src/a.vue',
        source: '<style scoped>\n:deep(.el-button) { color: var(--bms-color-primary); }\n</style>',
      },
      { path: 'src/b.vue', source: '<style scoped>\n.x { background: hsl(${hue} 65% 45%); }\n</style>' },
    ]
    expect(scanSourceFiles(files)).toEqual([])
  })

  it('产物面被拦截（CSS 未作用域化 / 全局选择器 / 硬编码色值 / 自有 JS 块全局污染）', () => {
    const problems = scanProductFiles({
      css: [
        { path: 'assets/a.css', source: '.demo__text{color:#123456}' },
        { path: 'assets/b.css', source: 'body[data-v-1]{margin:0}' },
      ],
      js: [
        { path: 'assets/module-x.js', source: 'window.addEventListener("resize",()=>{})' },
        { path: 'assets/DemoHome-x.js', source: 'document.body.appendChild(x)' },
      ],
    })
    expect(problems.length).toBeGreaterThanOrEqual(4)
  })

  it('产物 scoped 与令牌消费不误判', () => {
    expect(
      scanProductFiles({
        css: [
          {
            path: 'assets/a.css',
            source: '.demo__text[data-v-7d51d7e6]{color:var(--bms-color-text-secondary);margin:0 0 8px}',
          },
        ],
      }),
    ).toEqual([])
  })

  it('模块远端产物零违规（dist 存在时执行；CI 产物面由 module-build 兜底）', () => {
    const moduleDir = resolve(FRONTEND_DIR, 'modules/demo')
    if (!existsSync(resolve(moduleDir, 'dist'))) return
    expect(scanModuleProducts(FRONTEND_DIR)).toEqual([])
  })

  it('产物目标识别含暴露块与页面块（dist 存在时执行）', () => {
    const moduleDir = resolve(FRONTEND_DIR, 'modules/demo')
    if (!existsSync(resolve(moduleDir, 'dist'))) return
    const targets = collectProductTargets(moduleDir)
    expect(targets.css.length).toBeGreaterThan(0)
    expect(targets.js.some((file) => file.path.includes('module-'))).toBe(true)
    expect(targets.js.some((file) => file.path.includes('DemoHome'))).toBe(true)
  })
})
