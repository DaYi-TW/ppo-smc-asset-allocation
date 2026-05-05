/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_USE_MOCK?: string
  readonly VITE_API_BASE_URL?: string
  readonly VITE_SSE_BASE_URL?: string
  readonly VITE_AUTH_PROVIDER_URL?: string
  readonly VITE_DEMO_JWT?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
