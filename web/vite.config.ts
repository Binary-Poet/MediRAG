import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    proxy: {
      // 后端 API 反向代理，前端统一走 /api 前缀
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      // 健康检查（后端挂在根路径、无 /api 前缀）：顶栏服务状态灯轮询用
      '/health': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
