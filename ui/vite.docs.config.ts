import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  base: '/docs/',
  plugins: [react(), tailwindcss()],
  root: '.',
  publicDir: false,
  build: {
    outDir: 'dist/docs',
    emptyOutDir: true,
    rollupOptions: {
      input: path.resolve(__dirname, 'docs.html'),
      output: {
        entryFileNames: 'assets/index.js',
        chunkFileNames: 'assets/[name].js',
        assetFileNames: 'assets/[name][extname]',
      },
    },
  },
})
