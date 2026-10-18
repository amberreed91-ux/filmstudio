import { createServer as createHttpServer, request as httpRequest, type IncomingHttpHeaders, type Server } from 'node:http'
import type { AddressInfo } from 'node:net'
import { readFile } from 'node:fs/promises'
import { afterEach, describe, expect, it } from 'vitest'
import { createServer as createViteServer, type ViteDevServer } from 'vite'
import {
  createAuthenticatedCreatorWorkspaceProxy,
  validateCreatorWorkspaceRuntimeTarget,
} from '../creatorWorkspaceRouting'

type CapturedRequest = { method: string; url: string; headers: IncomingHttpHeaders; body: string }
type Upstream = { server: Server; target: string; requests: CapturedRequest[] }

async function startUpstream(): Promise<Upstream> {
  const requests: CapturedRequest[] = []
  const server = createHttpServer((request, response) => {
    const chunks: Buffer[] = []
    request.on('data', chunk => chunks.push(Buffer.from(chunk)))
    request.on('end', () => {
      requests.push({
        method: request.method ?? '',
        url: request.url ?? '',
        headers: request.headers,
        body: Buffer.concat(chunks).toString('utf8'),
      })
      response.writeHead(200, { 'Content-Type': 'application/json' })
      response.end(JSON.stringify({ accepted: true }))
    })
  })
  await new Promise<void>((resolve, reject) => {
    server.once('error', reject)
    server.listen(0, '127.0.0.1', resolve)
  })
  const address = server.address() as AddressInfo
  return { server, target: `http://127.0.0.1:${address.port}`, requests }
}

let vite: ViteDevServer | undefined
let runtime: Upstream | undefined
let auth: Upstream | undefined

afterEach(async () => {
  await vite?.close()
  await Promise.all([runtime, auth].filter((upstream): upstream is Upstream => Boolean(upstream))
    .map(({ server }) => new Promise<void>(resolve => server.close(() => resolve()))))
  vite = undefined
  runtime = undefined
  auth = undefined
})

async function startRoutingServer() {
  runtime = await startUpstream()
  auth = await startUpstream()
  vite = await createViteServer({
    configFile: false,
    appType: 'custom',
    server: {
      host: '127.0.0.1',
      port: 0,
      strictPort: true,
      allowedHosts: true,
      proxy: createAuthenticatedCreatorWorkspaceProxy(auth.target, runtime.target),
    },
    optimizeDeps: { noDiscovery: true, include: [] },
  })
  await vite.listen()
  const address = vite.httpServer?.address() as AddressInfo
  return `http://127.0.0.1:${address.port}`
}

const browserHeaders = {
  Host: 'studio.example.test:5179',
  Origin: 'http://studio.example.test:5179',
  Cookie: 'session_id=existing-session-value',
  Referer: 'http://studio.example.test:5179/creator-workspace',
}

async function requestThroughVite(baseUrl: string, path: string, method = 'GET') {
  const url = new URL(path, baseUrl)
  return new Promise<{ status: number; text: string }>((resolve, reject) => {
    const request = httpRequest(url, { method, headers: browserHeaders }, response => {
      const chunks: Buffer[] = []
      response.on('data', chunk => chunks.push(Buffer.from(chunk)))
      response.on('end', () => resolve({
        status: response.statusCode ?? 0,
        text: Buffer.concat(chunks).toString('utf8'),
      }))
    })
    request.once('error', reject)
    request.end()
  })
}

describe('authenticated Creator Workspace development routing', () => {
  it('sends the browser-relative F51 direction URL only to the dedicated runtime and preserves request identity headers', async () => {
    const baseUrl = await startRoutingServer()
    const response = await requestThroughVite(
      baseUrl,
      '/api/f51/studio/projects/project-a/scenes/scene-a/direction?view=current',
    )

    expect(response.status).toBe(200)
    expect(runtime?.requests).toHaveLength(1)
    expect(runtime?.requests[0]).toMatchObject({
      method: 'GET',
      url: '/api/f51/studio/projects/project-a/scenes/scene-a/direction?view=current',
    })
    expect(runtime?.requests[0].headers.host).toBe(browserHeaders.Host)
    expect(runtime?.requests[0].headers.origin).toBe(browserHeaders.Origin)
    expect(runtime?.requests[0].headers.cookie).toBe(browserHeaders.Cookie)
    expect(runtime?.requests[0].headers.referer).toBe(browserHeaders.Referer)
    expect(runtime?.requests[0].headers.authorization).toBeUndefined()
    expect(runtime?.requests[0].headers['x-session-token']).toBeUndefined()
    expect(runtime?.requests[0].headers['x-access-user-id']).toBeUndefined()
    expect(auth?.requests).toHaveLength(0)
  })

  it('proxies only the exact scoped direction and setting-reference methods', async () => {
    const baseUrl = await startRoutingServer()
    const routes: Array<[string, string]> = [
      ['GET', '/api/f51/studio/projects/p/scenes/s/direction'],
      ['PUT', '/api/f51/studio/projects/p/scenes/s/direction'],
      ['GET', '/api/f51/studio/projects/p/setting-references/setting'],
      ['POST', '/api/f51/studio/projects/p/setting-references/setting'],
      ['POST', '/api/f51/studio/projects/p/setting-references/setting/upload'],
      ['POST', '/api/f51/studio/projects/p/setting-references/setting/ref/approve'],
      ['POST', '/api/f51/studio/projects/p/setting-references/setting/ref/canonical'],
    ]

    for (const [method, path] of routes) {
      expect((await requestThroughVite(baseUrl, path, method)).status).toBe(200)
    }
    expect(runtime?.requests.map(({ method, url }) => [method, url])).toEqual(routes)
    for (const request of runtime?.requests ?? []) {
      expect(request.headers.host).toBe(browserHeaders.Host)
      expect(request.headers.origin).toBe(browserHeaders.Origin)
      expect(request.headers.cookie).toBe(browserHeaders.Cookie)
      expect(request.headers.referer).toBe(browserHeaders.Referer)
    }
    expect(auth?.requests).toHaveLength(0)
  })

  it('leaves unrelated APIs, broad project APIs, and unsupported methods outside the runtime proxy', async () => {
    const baseUrl = await startRoutingServer()
    const excluded = [
      '/api/health',
      '/api/projects/project-a/scenes/scene-a/direction',
      '/api/f51/studio/projects/project-a/screening/outputs',
      '/api/f51/studio/projects/project-a/scenes/scene-a/direction/extra',
    ]

    for (const path of excluded) await requestThroughVite(baseUrl, path)
    await requestThroughVite(baseUrl, '/api/f51/studio/projects/project-a/scenes/scene-a/direction', 'POST')
    expect(runtime?.requests).toHaveLength(0)
    expect(auth?.requests).toHaveLength(0)
  })

  it('keeps existing session endpoints on the explicitly configured auth-capable upstream', async () => {
    const baseUrl = await startRoutingServer()
    const authRoutes: Array<[string, string]> = [
      ['GET', '/api/f51/studio/auth/access-mode'],
      ['GET', '/api/f51/studio/auth/session'],
      ['DELETE', '/api/f51/studio/auth/session'],
      ['POST', '/api/f51/studio/auth/login'],
      ['POST', '/api/f51/studio/auth/register'],
      ['POST', '/api/f51/studio/auth/logout'],
    ]

    for (const [method, path] of authRoutes) {
      await requestThroughVite(baseUrl, path, method)
    }
    expect(auth?.requests.map(({ method, url }) => [method, url])).toEqual(authRoutes)
    expect(auth?.requests.every(request => request.headers.cookie === browserHeaders.Cookie)).toBe(true)
    expect(runtime?.requests).toHaveLength(0)
  })

  it('keeps the isolated runtime boundary separate from Studio lifespan and rejects hidden identity/ownership injection', async () => {
    const config = await readFile(new URL('../vite.creator-workspace-authenticated.config.ts', import.meta.url), 'utf8')
    const routing = await readFile(new URL('../creatorWorkspaceRouting.ts', import.meta.url), 'utf8')

    expect(config).not.toMatch(/backendSupervisorPlugin|from ['\"]\.\/backendSupervisor|main\.py|DatabaseStorage|project_store|recovery|worker|8010/i)
    expect(config).not.toContain("'/api':")
    expect(routing).toContain('validateCreatorWorkspaceRuntimeTarget')
    expect(routing).not.toMatch(/(?:x-session-token|authorization|access_user_id|user_id|ownership|bypass.?auth|hardcoded user)/i)
    expect(routing).not.toContain('project_5907c60cddbc')
    expect(routing).toContain('changeOrigin: false')
  })

  it('rejects the production and fixture ports as runtime targets', () => {
    expect(() => validateCreatorWorkspaceRuntimeTarget('http://127.0.0.1:9000', 'http://127.0.0.1:8010')).toThrow(/distinct loopback/)
    expect(() => validateCreatorWorkspaceRuntimeTarget('http://127.0.0.1:9000', 'http://127.0.0.1:8011')).toThrow(/distinct loopback/)
    expect(() => validateCreatorWorkspaceRuntimeTarget('http://127.0.0.1:9000', 'http://127.0.0.1:8012')).not.toThrow()
  })

  it('preserves proxy security semantics and adds no authentication or ownership bypass', async () => {
    const authTarget = 'http://127.0.0.1:9000'
    const routeMap = createAuthenticatedCreatorWorkspaceProxy(authTarget)
    const creatorRoutes = Object.entries(routeMap).filter(([route]) => route.includes('projects'))

    expect(creatorRoutes.length).toBeGreaterThan(0)
    for (const [, options] of creatorRoutes) {
      expect(options.changeOrigin).toBe(false)
      expect(options.xfwd).toBe(false)
      expect(options.rewriteWsOrigin).not.toBe(true)
      expect(options.headers).toBeUndefined()
      expect(options.rewrite).toBeUndefined()
      expect(options.auth).toBeUndefined()
      expect(options.target).toBe('http://127.0.0.1:8012')
    }
    const routingSource = await readFile(new URL('../creatorWorkspaceRouting.ts', import.meta.url), 'utf8')
    expect(routingSource).not.toMatch(/(?:x-session-token|authorization|access_user_id|access-owned-projects|hardcoded user)/i)
    expect(routingSource).not.toContain('project_5907c60cddbc')
    expect(routingSource).not.toContain("'/api':")
  })

  it('keeps routing isolated from the normal Studio config, fixture config, and port 8010', async () => {
    const config = await readFile(new URL('../vite.creator-workspace-authenticated.config.ts', import.meta.url), 'utf8')
    const normalConfig = await readFile(new URL('../vite.config.ts', import.meta.url), 'utf8')
    const fixtureConfig = await readFile(new URL('../vite.creator-workspace-fixture.config.ts', import.meta.url), 'utf8')

    expect(config).not.toContain('backendSupervisorPlugin')
    expect(config).not.toContain("'/api':")
    expect(normalConfig).toContain("target: 'http://127.0.0.1:8010'")
    expect(fixtureConfig).toContain('changeOrigin: true')
    expect(fixtureConfig).toContain('8011')
  })
})
