import { fileURLToPath, URL } from 'node:url'

import { VantResolver } from '@vant/auto-import-resolver'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { defineConfig } from 'vite'

// BMS 移动端 H5：固定开发端口 5174；/api 与 /healthz 代理 backend，/info 重写至 backend 根（连通验证）
export default defineConfig({
  plugins: [vue(), Components({ resolvers: [VantResolver()] })],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
      // 基座新体系（源码直出包）：与包 exports 设定一致（S4c 切流）
      '@bms/core': fileURLToPath(new URL('../../packages/core/src/index.ts', import.meta.url)),
      '@bms/vue': fileURLToPath(new URL('../../packages/vue/src/index.ts', import.meta.url)),
      '@bms/ui-vant': fileURLToPath(new URL('../../packages/ui-vant/src/index.ts', import.meta.url)),
    },
  },
  build: {
    rollupOptions: {
      output: {
        // 手动分包：第三方大件与基座源码独立 chunk（主包/页面包体积可控，预算可校验）
        manualChunks: (id: string): string | undefined => {
          if (id.includes('node_modules/vant') || id.includes('node_modules/@vant')) {
            return 'vendor-vant'
          }
          if (id.includes('/packages/')) {
            return 'bms-base'
          }
          return undefined
        },
      },
    },
  },
  server: {
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': { target: 'http://localhost:8000', changeOrigin: true },
      '/healthz': { target: 'http://localhost:8000', changeOrigin: true },
      '/info': { target: 'http://localhost:8000', changeOrigin: true, rewrite: () => '/' },
    },
  },
})
