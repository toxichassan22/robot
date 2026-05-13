import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import tsconfigPaths from "vite-tsconfig-paths";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "")
  const apiProxyTarget = env.VITE_API_PROXY_TARGET || 'http://127.0.0.1:8000'
  const sdLogicProxyTarget = env.VITE_SDLOGIC_PROXY_TARGET || 'http://127.0.0.1:8000'

  const toOrigin = (raw: string): string | null => {
    const s = String(raw || "").trim()
    if (!s) return null
    try {
      const u = new URL(s)
      return u.origin
    } catch {
      return null
    }
  }

  const whitelistRaw = String(env.LOCAL_TESTER_OLLAMA_URL_WHITELIST || process.env.LOCAL_TESTER_OLLAMA_URL_WHITELIST || "").trim()
  const whitelistItems = whitelistRaw
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean)

  const extraCandidates = [
    ...whitelistItems,
    String(env.BRAIN_OLLAMA_BASE_URL || process.env.BRAIN_OLLAMA_BASE_URL || "").trim(),
  ].filter(Boolean)

  const extraOrigins = Array.from(new Set(extraCandidates.map((x) => toOrigin(x)).filter((x): x is string => Boolean(x))))

  const connectSrc = [
    "'self'",
    "http://127.0.0.1:*",
    "http://localhost:*",
    "ws://127.0.0.1:*",
    "ws://localhost:*",
    ...extraOrigins,
  ].join(" ")

  const csp = [
    "default-src 'self'",
    "base-uri 'self'",
    "object-src 'none'",
    "frame-ancestors 'none'",
    "img-src 'self' data: blob:",
    "font-src 'self' data: https://fonts.gstatic.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'",
    `connect-src ${connectSrc}`,
  ].join("; ") + ";"

  const proxy = {
    '/api': {
      target: apiProxyTarget,
      changeOrigin: true,
      secure: false,
      timeout: 0,
      proxyTimeout: 0,
    },
    '/v1': {
      target: sdLogicProxyTarget,
      changeOrigin: true,
      secure: false,
      timeout: 0,
      proxyTimeout: 0,
    }
  }

  return {

    plugins: [
      react(),
      tsconfigPaths(),
    ],
    root: 'frontend',
    build: {
      outDir: '../dist',
      emptyOutDir: true,
    },
    server: {
      host: "0.0.0.0",
      allowedHosts: true,
      headers: {
        "Content-Security-Policy": csp,
      },
      proxy,
    },
    preview: {
      host: "0.0.0.0",
      allowedHosts: true,
      headers: {
        "Content-Security-Policy": csp,
      },
      proxy,
    },
  }
})
