import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// Minimal Vite config for the SafePath React frontend.
// Dev server defaults to http://localhost:5173 (whitelisted in the backend CORS config).
export default defineConfig({
  plugins: [react()],
})
