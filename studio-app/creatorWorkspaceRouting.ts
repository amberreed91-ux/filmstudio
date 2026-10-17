import type { IncomingMessage } from 'node:http'
import type { ProxyOptions } from 'vite'

export const CREATOR_WORKSPACE_RUNTIME_TARGET = 'http://127.0.0.1:8012'

export function validateCreatorWorkspaceRuntimeTarget(authTarget: string, runtimeTarget: string): void {
  const runtime = new URL(runtimeTarget)
  const auth = new URL(authTarget)
  if (!['127.0.0.1', 'localhost', '[::1]'].includes(runtime.hostname)
    || runtime.port === '8010' || runtime.port === '8011'
    || runtime.origin === auth.origin) {
    throw new Error('Creator Workspace runtime must be a distinct loopback origin, not a Studio or fixture backend')
  }
}

const withOptionalQuery = (path: string) => `^${path}(?:\\?[^#]*)?$`
const projectScene = '/api/f51/studio/projects/[^/?]+/scenes/[^/?]+'
const settingReferences = '/api/f51/studio/projects/[^/?]+/setting-references/[^/?]+'

function methodGate(allowedMethods: readonly string[]) {
  return (request: IncomingMessage) => allowedMethods.includes(request.method ?? '') ? undefined : false
}

function proxy(target: string, methods: readonly string[]): ProxyOptions {
  return {
    target,
    // Keep the browser-visible host/origin context for the existing Origin check.
    changeOrigin: false,
    xfwd: false,
    bypass: methodGate(methods),
  }
}

/**
 * Narrow development routing only. The Studio auth endpoints stay on the
 * existing auth-capable backend; only these Creator Workspace routes go to
 * the isolated runtime. Vite's proxy relays Cookie, Origin, and Referer as-is.
 */
export function createAuthenticatedCreatorWorkspaceProxy(
  authTarget: string,
  runtimeTarget = CREATOR_WORKSPACE_RUNTIME_TARGET,
): Record<string, ProxyOptions> {
  return {
    [withOptionalQuery(`${projectScene}/direction`)]: proxy(runtimeTarget, ['GET', 'PUT']),
    [withOptionalQuery(settingReferences)]: proxy(runtimeTarget, ['GET', 'POST']),
    [withOptionalQuery(`${settingReferences}/upload`)]: proxy(runtimeTarget, ['POST']),
    [withOptionalQuery(`${settingReferences}/[^/?]+/approve`)]: proxy(runtimeTarget, ['POST']),
    [withOptionalQuery(`${settingReferences}/[^/?]+/canonical`)]: proxy(runtimeTarget, ['POST']),

    // These exact session endpoints retain the existing authentication flow.
    [withOptionalQuery('/api/f51/studio/auth/access-mode')]: proxy(authTarget, ['GET']),
    [withOptionalQuery('/api/f51/studio/auth/session')]: proxy(authTarget, ['GET', 'DELETE']),
    [withOptionalQuery('/api/f51/studio/auth/login')]: proxy(authTarget, ['POST']),
    [withOptionalQuery('/api/f51/studio/auth/register')]: proxy(authTarget, ['POST']),
    [withOptionalQuery('/api/f51/studio/auth/logout')]: proxy(authTarget, ['POST']),
  }
}
