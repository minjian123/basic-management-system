import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import Components from 'unplugin-vue-components/vite'
import { VantResolver } from 'unplugin-vue-components/resolvers'

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    vue(),
    // Vant 按需自动导入组件与样式
    Components({
      resolvers: [VantResolver()],
      dts: 'src/components.d.ts',
    }),
  ],
  // dev 模式下将 /healthz 代理到后端服务（后端默认端口 8000）
  server: {
    proxy: {
      '/healthz': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  test: {
    environment: 'jsdom',
  },
})
