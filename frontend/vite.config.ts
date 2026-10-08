/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
    // Keep tests offline: never hit the live RAG API from .env.local (connection refused → mock fallback).
    env: { VITE_USE_MOCKS: 'true', VITE_RAG_API_URL: 'http://127.0.0.1:9', VITE_API_BASE_URL: 'http://127.0.0.1:9' },
  },
})
