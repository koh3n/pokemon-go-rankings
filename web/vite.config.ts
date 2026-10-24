import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// base './' keeps asset and data URLs relative, so the built site works from any folder or static host.
export default defineConfig({
  base: './',
  plugins: [react()],
})
