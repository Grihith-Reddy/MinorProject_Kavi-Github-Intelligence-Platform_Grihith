import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173
  },
  build: {
    outDir: 'dist',
    cssMinify: 'esbuild',
    rollupOptions: {
      output: {
        manualChunks: (id: string) => {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/react/') || id.includes('/react-dom/') || id.includes('/react-router-dom/')) {
            return 'vendor-react'
          }
          if (id.includes('/framer-motion/')) return 'vendor-motion'
          if (id.includes('/firebase/')) return 'vendor-auth'
          if (id.includes('/lucide-react/')) return 'vendor-ui'
          if (id.includes('/axios/')) return 'vendor-http'
          return undefined
        }
      }
    }
  }
})
