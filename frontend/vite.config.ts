import { fileURLToPath, URL } from 'node:url'
import { createRequire } from 'node:module'

import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import vueDevTools from 'vite-plugin-vue-devtools'

// https://vite.dev/config/
export default defineConfig(() => {
  const require = createRequire(import.meta.url)
  const useHttps = String(process.env.VITE_DEV_HTTPS || '').toLowerCase() === 'true'
  const plugins = [vue(), vueDevTools()]

  if (useHttps) {
    try {
      const basicSsl = require('@vitejs/plugin-basic-ssl').default
      plugins.push(basicSsl())
    } catch {
      // Keep running without SSL plugin if dependency is not installed yet.
      console.warn('[vite] @vitejs/plugin-basic-ssl is not installed. Run: npm i -D @vitejs/plugin-basic-ssl')
    }
  }

  return {
    plugins,
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      },
    },
    server: {
      https: useHttps ? {} : undefined,
      proxy: {
        // Java Auth 서버 로그인/회원가입
        '/auth': {
          target: 'http://localhost:8081',
          changeOrigin: true,
        },
        // '/api'로 시작하는 요청은 FastAPI AI 서버(8000)로 보냅니다.
        '/api': {
          target: 'http://localhost:8000',
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api/, '/api/v1')
        },
        // '/static'으로 시작하는 요청도 FastAPI AI 서버(8000)로 보냅니다. (PDF 리포트 다운로드용)
        '/static': {
          target: 'http://localhost:8000',
          changeOrigin: true,
        }
      }
    }
  }
})
