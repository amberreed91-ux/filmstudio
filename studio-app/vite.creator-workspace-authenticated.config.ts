import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import {
  createAuthenticatedCreatorWorkspaceProxy,
  CREATOR_WORKSPACE_RUNTIME_TARGET,
  validateCreatorWorkspaceRuntimeTarget,
} from './creatorWorkspaceRouting'

function requiredLoopbackTarget(name: string): string {
  const value = process.env[name]
  if (!value) {
    throw new Error(`${name} must point to the existing local Studio auth-capable runtime`)
  }

  let target: URL
  try {
    target = new URL(value)
  } catch {
    throw new Error(`${name} must be an absolute HTTP(S) URL`)
  }
  if (!['http:', 'https:'].includes(target.protocol)
    || !['127.0.0.1', 'localhost', '[::1]'].includes(target.hostname)
    || target.username || target.password || target.pathname !== '/' || target.search || target.hash) {
    throw new Error(`${name} must be a credential-free loopback HTTP(S) origin`)
  }
  return target.origin
}

/**
 * Authenticated routing development config. It intentionally omits the normal
 * backend supervisor and every broad Studio API proxy. Auth remains on the
 * existing auth-capable service; only the exact Creator Workspace methods are
 * sent to the isolated runtime.
 */
export default defineConfig(() => {
  const authTarget = requiredLoopbackTarget('CREATOR_WORKSPACE_AUTH_TARGET')
  const runtimeTarget = process.env.CREATOR_WORKSPACE_RUNTIME_TARGET
    ? requiredLoopbackTarget('CREATOR_WORKSPACE_RUNTIME_TARGET')
    : CREATOR_WORKSPACE_RUNTIME_TARGET
  validateCreatorWorkspaceRuntimeTarget(authTarget, runtimeTarget)

  return {
    base: '/',
    plugins: [tailwindcss(), react()],
    server: {
      host: '127.0.0.1',
      port: 5179,
      strictPort: true,
      allowedHosts: ['localhost', '127.0.0.1'],
      proxy: createAuthenticatedCreatorWorkspaceProxy(authTarget, runtimeTarget),
    },
  }
})
