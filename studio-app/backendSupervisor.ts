import { existsSync } from 'node:fs'
import { spawn } from 'node:child_process'
import type { ServerResponse } from 'node:http'
import { fileURLToPath } from 'node:url'
import type { Connect, Plugin } from 'vite'

export const BACKEND_RESTART_PATH = '/__studio/backend/restart'
const ADMIN_TOKEN = 'studio-restart-2026'
const BACKEND_DIR = fileURLToPath(new URL('../studio-backend/', import.meta.url))

function sendJson(response: ServerResponse, status: number, body: Record<string, unknown>) {
  response.statusCode = status
  response.setHeader('Content-Type', 'application/json')
  response.end(JSON.stringify(body))
}

function backendPython(): string | null {
  const candidates = [
    fileURLToPath(new URL('../studio-backend/.venv/bin/python', import.meta.url)),
    fileURLToPath(new URL('../.venv/bin/python', import.meta.url)),
  ]
  return candidates.find(existsSync) ?? null
}

export function backendSupervisorMiddleware(): Connect.NextHandleFunction {
  return (request, response, next) => {
    if (request.url?.split('?')[0] !== BACKEND_RESTART_PATH) {
      next()
      return
    }
    if (!['127.0.0.1', '::1', '::ffff:127.0.0.1'].includes(request.socket.remoteAddress ?? '')) {
      sendJson(response, 403, { detail: 'Backend startup requires a local connection' })
      return
    }
    if (request.method !== 'POST') {
      sendJson(response, 405, { detail: 'Method not allowed' })
      return
    }
    if (request.headers['x-admin-token'] !== ADMIN_TOKEN) {
      sendJson(response, 403, { detail: 'Invalid admin token' })
      return
    }

    const python = backendPython()
    if (!python) {
      sendJson(response, 500, { detail: 'Backend Python environment was not found' })
      return
    }

    try {
      const child = spawn(
        python,
        ['-m', 'uvicorn', 'main:app', '--host', '127.0.0.1', '--port', '8010', '--log-level', 'info'],
        {
          cwd: BACKEND_DIR,
          env: { ...process.env, STUDIO_ACCESS_MODE: 'local', RATE_LIMIT_PER_MINUTE: process.env.RATE_LIMIT_PER_MINUTE || '600' },
          detached: true,
          stdio: 'ignore',
        },
      )
      child.unref()
      sendJson(response, 202, { message: 'Backend startup requested' })
    } catch (error) {
      sendJson(response, 500, {
        detail: error instanceof Error ? error.message : 'Unable to start backend',
      })
    }
  }
}

export function backendSupervisorPlugin(): Plugin {
  const install = (server: { middlewares: Connect.Server }) => {
    server.middlewares.use(backendSupervisorMiddleware())
  }
  return {
    name: 'studio-backend-supervisor',
    configureServer: install,
    configurePreviewServer: install,
  }
}
