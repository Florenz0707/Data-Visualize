import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000', // 假设你的后端运行在 8000
        changeOrigin: true,
        // 如果后端路径没有 /api 前缀，需要 rewrite: (path) => path.replace(/^\/api/, '')
      }
    }
  }
})