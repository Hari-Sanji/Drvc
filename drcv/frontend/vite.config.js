import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: { port: 5173, proxy: { '/api': 'http://localhost:8000' } },
  build: {
    chunkSizeWarningLimit: 900,
    rollupOptions: { output: { manualChunks: { flow: ['@xyflow/react', 'd3-force'], vendor: ['react', 'react-dom', 'react-router-dom'] } } },
  },
})
