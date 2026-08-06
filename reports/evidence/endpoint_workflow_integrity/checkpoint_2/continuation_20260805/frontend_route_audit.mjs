import fs from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(path.join(process.cwd(), 'package.json'))
const ts = require('typescript')

const sourceRoot = path.resolve('src')
const openApiUrl = process.env.CHECKPOINT_2_OPENAPI_URL || 'http://127.0.0.1:8023/openapi.json'
const callNames = new Set(['fetch', 'fetchJson', 'fetchExport', 'fetchStitch'])
const legacyNonPriorityPaths = [
  /^POST \/api\/f51\/studio\/projects\/\{\}\/share\/(generate|collaborator)$/,
  /^POST \/api\/f51\/studio\/scenes\/\{\}\/comments$/,
  /^DELETE \/api\/f51\/studio\/scenes\/\{\}\/comments\/\{\}$/,
  /^POST \/api\/f51\/studio\/scenes\/\{\}\/approval$/,
  /^GET \/api\/f51\/studio\/projects\/\{\}\/activity$/,
  /^GET \/api\/f51\/studio\/share\/\{\}$/,
]
const exportPackageTypes = [
  'pitch-pack',
  'shot-list',
  'prompt-pack',
  'cut-manifest',
  'archive-snapshot',
  'festival-export',
  'youtube-export',
  'trailer-export',
  'teaser-export',
  'subtitle-packages',
]

function sourceFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const entryPath = path.join(directory, entry.name)
    if (entry.isDirectory()) return sourceFiles(entryPath)
    if (!/\.(ts|tsx)$/.test(entry.name) || /\.test\.(ts|tsx)$/.test(entry.name)) return []
    return [entryPath]
  })
}

function renderExpression(node, source) {
  if (!node) return null
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node)) return node.text
  if (ts.isTemplateExpression(node)) {
    let rendered = node.head.text
    for (const span of node.templateSpans) {
      const expression = span.expression.getText(source)
      if (!/query|searchparams|\bparams\b|\?[^:]+:/i.test(expression)) rendered += '{}'
      rendered += span.literal.text
    }
    return rendered
  }
  if (
    ts.isCallExpression(node)
    && ts.isIdentifier(node.expression)
    && node.expression.text === 'buildStudioApiUrl'
  ) {
    return renderExpression(node.arguments[0], source)
  }
  if (ts.isBinaryExpression(node) && node.operatorToken.kind === ts.SyntaxKind.PlusToken) {
    const left = renderExpression(node.left, source)
    const right = renderExpression(node.right, source)
    return left !== null && right !== null ? left + right : null
  }
  return null
}

function requestMethod(node) {
  if (!node || !ts.isObjectLiteralExpression(node)) return 'GET'
  for (const property of node.properties) {
    if (!ts.isPropertyAssignment(property)) continue
    if (property.name.getText().replace(/['"]/g, '') !== 'method') continue
    if (ts.isStringLiteral(property.initializer)) return property.initializer.text.toUpperCase()
  }
  return 'GET'
}

function normalizePath(value) {
  return (value.replace(/\{[^}]+\}/g, '{}').replace(/\/$/, '') || '/')
}

const calls = []
for (const file of sourceFiles(sourceRoot)) {
  const source = ts.createSourceFile(
    file,
    fs.readFileSync(file, 'utf8'),
    ts.ScriptTarget.Latest,
    true,
  )
  function visit(node) {
    if (ts.isCallExpression(node)) {
      let name = ''
      if (ts.isIdentifier(node.expression)) name = node.expression.text
      if (ts.isPropertyAccessExpression(node.expression)) name = node.expression.name.text
      if (callNames.has(name)) {
        let value = renderExpression(node.arguments[0], source)
        if (value) {
          const apiIndex = value.indexOf('/api/')
          const projectsIndex = value.indexOf('/projects/')
          const start = apiIndex >= 0 ? apiIndex : projectsIndex
          if (start >= 0) {
            value = value.slice(start).split('?')[0]
            const position = source.getLineAndCharacterOfPosition(node.getStart())
            calls.push({
              file: path.relative(process.cwd(), file),
              line: position.line + 1,
              method: requestMethod(node.arguments[1]),
              path: value,
            })
          }
        }
      }
    }
    ts.forEachChild(node, visit)
  }
  visit(source)
}

const response = await fetch(openApiUrl)
if (!response.ok) throw new Error(`OpenAPI request failed: ${response.status}`)
const schema = await response.json()
const operations = new Set()
for (const [routePath, pathItem] of Object.entries(schema.paths)) {
  for (const method of Object.keys(pathItem)) {
    if (['get', 'post', 'put', 'patch', 'delete'].includes(method)) {
      operations.add(`${method.toUpperCase()} ${normalizePath(routePath)}`)
    }
  }
}

const unmatched = calls.filter(
  (call) => !operations.has(`${call.method} ${normalizePath(call.path)}`),
)
const dynamicExport = unmatched.filter(
  (call) => `${call.method} ${normalizePath(call.path)}` === 'GET /api/f51/studio/exports/{}/{}',
)
const missingExportTypes = exportPackageTypes.filter(
  (packageType) => !operations.has(`GET /api/f51/studio/exports/{}/${packageType}`),
)
const legacy = unmatched.filter((call) => legacyNonPriorityPaths.some(
  (pattern) => pattern.test(`${call.method} ${normalizePath(call.path)}`),
))
const unexpected = unmatched.filter((call) => !dynamicExport.includes(call) && !legacy.includes(call))

console.log(`production_client_calls_parsed=${calls.length}`)
console.log(`production_client_calls_directly_matched=${calls.length - unmatched.length}`)
console.log(`dynamic_export_clients=${dynamicExport.length}`)
console.log(`dynamic_export_missing_static_routes=${missingExportTypes.length}`)
console.log(`legacy_non_priority_unmatched=${legacy.length}`)
for (const call of legacy) {
  console.log(`legacy_dependency=${call.method} ${call.path} ${call.file}:${call.line}`)
}
console.log(`unexpected_priority_unmatched=${unexpected.length}`)
for (const call of unexpected) {
  console.log(`unexpected=${call.method} ${call.path} ${call.file}:${call.line}`)
}

const passed = missingExportTypes.length === 0 && unexpected.length === 0
console.log(`status=${passed ? 'PASS' : 'FAIL'}`)
process.exitCode = passed ? 0 : 1
