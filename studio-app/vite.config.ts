import type { IncomingMessage } from 'node:http'
import { defineConfig } from 'vite'
import type { ProxyOptions } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { backendSupervisorPlugin } from './backendSupervisor'

/*
 * TEMPORARY privacy-safe diagnostic instrumentation for the Vite dev proxy
 * boundary of exactly: GET /api/f51/studio/auth/session
 *
 * Observational only. It attaches listeners to the existing `/api` proxy
 * server via the existing `configure` callback and emits fixed, allowlisted
 * records to the Vite process output. It never alters requests, responses,
 * headers, cookies, statuses, bodies, timeouts, or proxy options, and it
 * never reads or emits query values, raw URLs, headers, bodies, raw error
 * messages, or stack traces.
 *
 * CAVEAT: Vite's built-in proxy error handler (registered by Vite itself,
 * not here) still logs the raw request URL and the raw error stack to the
 * Vite process output on proxy errors. That pre-existing handler lives in
 * the installed Vite implementation and cannot be changed from
 * vite.config.ts without modifying dependency files, so Vite's own output
 * is NOT fully privacy sanitized. Only the records carrying the
 * [STUDIO_PROXY_DIAGNOSTIC] prefix below are sanitized.
 */

const STUDIO_SESSION_DIAGNOSTIC_PREFIX = '[STUDIO_PROXY_DIAGNOSTIC]'
const STUDIO_SESSION_PATH = '/api/f51/studio/auth/session'
const STUDIO_SESSION_UPSTREAM_HOST = '127.0.0.1'
const STUDIO_SESSION_UPSTREAM_PORT = 8010

type StudioSessionProxyDiagnosticEvent =
  | 'request_seen'
  | 'proxy_start'
  | 'socket_assigned'
  | 'socket_connected'
  | 'proxy_error'
  | 'upstream_response'
  | 'upstream_end'
  | 'downstream_finish'
  | 'downstream_close'
  | 'downstream_aborted'

// UPSTREAM_ERROR is part of the allowlist but reserved: every error code
// that is not one of the four pass-through codes normalizes to
// UNKNOWN_ERROR, so UPSTREAM_ERROR is never emitted.
type StudioSessionProxyDiagnosticErrorCode =
  | 'ECONNRESET'
  | 'ECONNREFUSED'
  | 'ETIMEDOUT'
  | 'EPIPE'
  | 'UPSTREAM_ERROR'
  | 'UNKNOWN_ERROR'

const STUDIO_SESSION_PASS_THROUGH_ERROR_CODES = [
  'ECONNRESET',
  'ECONNREFUSED',
  'ETIMEDOUT',
  'EPIPE',
] as const

type StudioSessionProxyServer = Parameters<NonNullable<ProxyOptions['configure']>>[0]

/**
 * True only for the single instrumented request: GET
 * /api/f51/studio/auth/session. The comparison operates on the pathname
 * only; any query string is discarded without being read or logged.
 */
function isStudioSessionProxyRequest(req: IncomingMessage): boolean {
  if (req.method !== 'GET') return false
  const rawUrl = req.url
  if (typeof rawUrl !== 'string') return false
  const queryIndex = rawUrl.indexOf('?')
  const pathname = queryIndex === -1 ? rawUrl : rawUrl.slice(0, queryIndex)
  return pathname === STUDIO_SESSION_PATH
}

/** Never reads or emits error.message or error.stack. */
function normalizeStudioSessionProxyErrorCode(
  error: unknown,
): StudioSessionProxyDiagnosticErrorCode {
  const code = (error as { code?: unknown } | null | undefined)?.code
  if (
    typeof code === 'string' &&
    (STUDIO_SESSION_PASS_THROUGH_ERROR_CODES as readonly string[]).includes(code)
  ) {
    return code as (typeof STUDIO_SESSION_PASS_THROUGH_ERROR_CODES)[number]
  }
  return 'UNKNOWN_ERROR'
}

function observedStatus(statusCode: number | undefined): number | undefined {
  return typeof statusCode === 'number' ? statusCode : undefined
}

/**
 * Emits one fixed-field record to the Vite process output. Fields are
 * limited to: utc, path, upstream_host, upstream_port, event, and (only
 * when actually observed) status / error. Errors are swallowed so the
 * instrumentation can never affect proxy behavior.
 */
function emitStudioSessionProxyDiagnostic(
  event: StudioSessionProxyDiagnosticEvent,
  detail?: {
    status?: number
    error?: StudioSessionProxyDiagnosticErrorCode
  },
): void {
  try {
    const record = [
      `utc=${new Date().toISOString()}`,
      `path=${STUDIO_SESSION_PATH}`,
      `upstream_host=${STUDIO_SESSION_UPSTREAM_HOST}`,
      `upstream_port=${STUDIO_SESSION_UPSTREAM_PORT}`,
      `event=${event}`,
    ]
    if (typeof detail?.status === 'number') {
      record.push(`status=${detail.status}`)
    }
    if (detail?.error !== undefined) {
      record.push(`error=${detail.error}`)
    }
    process.stdout.write(`${STUDIO_SESSION_DIAGNOSTIC_PREFIX} ${record.join(' ')}\n`)
  } catch {
    // Diagnostics must never alter or interrupt the proxied request.
  }
}

/**
 * Temporary observational instrumentation for GET
 * /api/f51/studio/auth/session on the existing `/api` proxy instance.
 * Listeners are additive: they never remove, replace, or reorder Vite's
 * own listeners, and they never modify req/res.
 *
 * Mapping to the installed Vite 8 / bundled http-proxy-3 implementation:
 * - "start" is the earliest event the implementation emits for a proxied
 *   web request (first statement of its stream pass), so request_seen and
 *   proxy_start are both recorded there, request_seen first.
 * - "proxyReq" fires when a socket is assigned (socket_assigned); TCP
 *   establishment is only claimed by the socket's "connect" event
 *   (socket_connected), or when the assigned socket is already an
 *   established, non-destroyed keep-alive connection.
 * - "proxyRes" proves an upstream HTTP response was received.
 * - "end" is the upstream response stream ending.
 * - "error" / "econnreset" surface proxy failures (pre vs post
 *   socket_connected is classified from the record order).
 * - downstream_finish / downstream_close / downstream_aborted are
 *   observed directly on the Vite response object.
 */
function configureStudioSessionProxyDiagnostics(proxy: StudioSessionProxyServer): void {
  proxy.on('start', (req, res) => {
    if (!isStudioSessionProxyRequest(req)) return
    emitStudioSessionProxyDiagnostic('request_seen')
    emitStudioSessionProxyDiagnostic('proxy_start')
    res.once('finish', () => {
      emitStudioSessionProxyDiagnostic('downstream_finish', {
        status: observedStatus(res.statusCode),
      })
    })
    res.once('close', () => {
      if (!res.writableFinished) {
        emitStudioSessionProxyDiagnostic('downstream_aborted')
      }
      emitStudioSessionProxyDiagnostic('downstream_close')
    })
  })

  proxy.on('proxyReq', (_proxyReq, req, _res, _options, socket) => {
    if (!isStudioSessionProxyRequest(req)) return
    emitStudioSessionProxyDiagnostic('socket_assigned')
    if (socket.connecting) {
      socket.once('connect', () => {
        emitStudioSessionProxyDiagnostic('socket_connected')
      })
    } else if (!socket.destroyed) {
      // Reused keep-alive socket: its TCP connection is already established.
      emitStudioSessionProxyDiagnostic('socket_connected')
    }
  })

  proxy.on('proxyRes', (proxyRes, req) => {
    if (!isStudioSessionProxyRequest(req)) return
    emitStudioSessionProxyDiagnostic('upstream_response', {
      status: observedStatus(proxyRes.statusCode),
    })
  })

  proxy.on('end', (req, _res, proxyRes) => {
    if (!isStudioSessionProxyRequest(req)) return
    emitStudioSessionProxyDiagnostic('upstream_end', {
      status: observedStatus(proxyRes.statusCode),
    })
  })

  const emitStudioSessionProxyError = (error: Error, req: IncomingMessage): void => {
    if (!isStudioSessionProxyRequest(req)) return
    emitStudioSessionProxyDiagnostic('proxy_error', {
      error: normalizeStudioSessionProxyErrorCode(error),
    })
  }
  proxy.on('error', emitStudioSessionProxyError)
  proxy.on('econnreset', emitStudioSessionProxyError)
}

export default defineConfig({
  base: '/',
  plugins: [
    backendSupervisorPlugin(),
    tailwindcss(),
    react(),
  ],
  build: {
    chunkSizeWarningLimit: 1000,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes('node_modules/react') || id.includes('node_modules/react-dom') || id.includes('node_modules/react-router')) {
            return 'vendor-react';
          }
          if (id.includes('node_modules/three') || id.includes('node_modules/@react-three')) {
            return 'vendor-three';
          }
          if (id.includes('node_modules/framer-motion') || id.includes('node_modules/lucide-react') || id.includes('node_modules/clsx')) {
            return 'vendor-ui';
          }
          if (id.includes('node_modules/recharts')) {
            return 'vendor-charts';
          }
          if (id.includes('node_modules/@tanstack/react-query')) {
            return 'vendor-query';
          }
        },
      },
    },
  },
  server: {
    port: 5001,
    host: '127.0.0.1',
    allowedHosts: ['localhost', '127.0.0.1'],
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        xfwd: true,
        configure: configureStudioSessionProxyDiagnostics,
      },
      '/health': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        xfwd: true,
      },
      '/projects': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        xfwd: true,
      },
      '/outputs': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        xfwd: true,
      },
      '/previs-assets': {
        target: 'http://127.0.0.1:8010',
        changeOrigin: true,
        xfwd: true,
      },
    },
  },
})
