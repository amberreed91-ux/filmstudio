// Temporary LAN access to the Mac's existing studio. The generated link grants
// local creator access; do not share it. No backend authentication is changed.
// Usage: STUDIO_PREVIEW_HOST=<Mac Wi-Fi IP> node scripts/mobile_preview.mjs
import http from 'node:http'
import { randomBytes, timingSafeEqual } from 'node:crypto'
import { createReadStream } from 'node:fs'
import { realpath, stat } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const dist = fileURLToPath(new URL('../studio-app/dist/', import.meta.url))
const mime = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.svg': 'image/svg+xml', '.webp': 'image/webp', '.ico': 'image/x-icon', '.woff2': 'font/woff2', '.mp4': 'video/mp4' }
const cookieName = 'studio_mobile_preview'

export function createPreviewServer({ host, port = 5002, token, backendPort = 8010, root = dist }) {
  const origin = `http://${host}:${port}`
  const matches = value => typeof value === 'string' && Buffer.byteLength(value) === Buffer.byteLength(token) && timingSafeEqual(Buffer.from(value), Buffer.from(token))
  return http.createServer(async (req, res) => {
    res.setHeader('Cache-Control', 'no-store')
    res.setHeader('Referrer-Policy', 'no-referrer')
    res.setHeader('X-Content-Type-Options', 'nosniff')
    res.setHeader('X-Frame-Options', 'DENY')
    const fail = (code, message) => { res.writeHead(code, { 'Content-Type': 'text/plain' }); res.end(message) }
    if (req.headers.host !== `${host}:${port}`) return fail(403, 'Unknown preview host')
    const url = new URL(req.url, origin)
    if (url.pathname === '/__preview/open' && req.method === 'GET') {
      if (!matches(url.searchParams.get('token'))) return fail(403, 'Open the preview link supplied on your Mac.')
      // HTTP is intentionally limited to the local Wi-Fi preview. Production
      // session cookies remain Secure; this separate cookie expires in 8 hours.
      res.writeHead(303, { Location: '/', 'Set-Cookie': `${cookieName}=${token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800` })
      return res.end()
    }
    if ((req.headers.origin && req.headers.origin !== origin) || req.headers['sec-fetch-site'] === 'cross-site') return fail(403, 'Cross-site preview request denied')
    const cookie = (req.headers.cookie || '').split(';').map(value => value.trim()).find(value => value.startsWith(`${cookieName}=`))?.slice(cookieName.length + 1)
    if (!matches(cookie)) return fail(403, 'Open the preview link supplied on your Mac.')
    if (url.pathname.startsWith('/__studio/')) return fail(403, 'Mac controls are unavailable in the phone preview.')
    if (/^\/(api|health|ready|build-info|outputs|previs-assets|static|projects)(\/|$)/.test(url.pathname)) {
      // Only the token-authenticated preview delegates to the existing local
      // creator session. Never forward untrusted client identity headers.
      const headers = { ...req.headers, host: `127.0.0.1:${backendPort}` }
      for (const name of Object.keys(headers)) {
        if (name.startsWith('x-forwarded-') || ['forwarded', 'cookie', 'authorization', 'x-session-token', 'origin', 'referer', 'connection'].includes(name)) delete headers[name]
      }
      const upstream = http.request({ hostname: '127.0.0.1', port: backendPort, path: url.pathname + url.search, method: req.method, headers, timeout: 300000 }, response => {
        const responseHeaders = { ...response.headers, 'cache-control': 'no-store' }
        delete responseHeaders['set-cookie']
        res.writeHead(response.statusCode, responseHeaders)
        response.pipe(res)
      })
      upstream.on('timeout', () => upstream.destroy(new Error('Backend timeout')))
      upstream.on('error', () => { if (!res.headersSent) fail(502, 'The studio backend is unavailable.'); else res.destroy() })
      res.on('close', () => upstream.destroy())
      req.pipe(upstream)
      return
    }
    if (!['GET', 'HEAD'].includes(req.method)) return fail(405, 'Method not allowed')
    try {
      const base = await realpath(root)
      let candidate = path.resolve(base, `.${decodeURIComponent(url.pathname)}`)
      if (!candidate.startsWith(base + path.sep) && candidate !== base) return fail(403, 'Invalid path')
      try { if (!(await stat(candidate)).isFile()) candidate = path.join(base, 'index.html') }
      catch { if (path.extname(candidate)) return fail(404, 'File not found'); candidate = path.join(base, 'index.html') }
      candidate = await realpath(candidate)
      if (!candidate.startsWith(base + path.sep)) return fail(403, 'Invalid path')
      const info = await stat(candidate)
      res.writeHead(200, { 'Content-Type': mime[path.extname(candidate)] || 'application/octet-stream', 'Content-Length': info.size })
      if (req.method === 'HEAD') return res.end()
      const stream = createReadStream(candidate)
      stream.on('error', () => res.destroy())
      stream.pipe(res)
    } catch { fail(500, 'Build the frontend with npm run build before starting the preview.') }
  })
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const host = process.env.STUDIO_PREVIEW_HOST
  if (!host) throw new Error('Set STUDIO_PREVIEW_HOST to your Mac Wi-Fi IP address.')
  const token = randomBytes(32).toString('hex')
  const server = createPreviewServer({ host, token })
  server.listen(5002, host, () => console.log(`Phone preview: http://${host}:5002/__preview/open?token=${token}\nKeep this link private. Expires in 8 hours. Ctrl+C stops the preview.`))
  setTimeout(() => { server.closeAllConnections(); server.close() }, 8 * 60 * 60 * 1000).unref()
}
