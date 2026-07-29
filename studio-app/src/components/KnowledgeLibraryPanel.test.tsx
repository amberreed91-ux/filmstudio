import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

import KnowledgeLibraryPanel from './KnowledgeLibraryPanel'

vi.mock('../lib/studioKnowledgeApi', () => ({
  buildKnowledgeContext: vi.fn(),
  listKnowledgeAtoms: vi.fn(() => Promise.resolve({ atoms: [] })),
  listKnowledgeBibles: vi.fn(() => Promise.resolve({ bibles: [] })),
  listKnowledgeConflicts: vi.fn(() => Promise.resolve({ conflicts: [] })),
  rebuildKnowledgeIndex: vi.fn(),
  registerKnowledgeBible: vi.fn(),
}))

describe('KnowledgeLibraryPanel', () => {
  it('renders the canonical knowledge workflow shell', () => {
    const html = renderToStaticMarkup(<KnowledgeLibraryPanel projectId="project-knowledge" />)

    expect(html).toContain('Canonical Knowledge')
    expect(html).toContain('Add Bible')
    expect(html).toContain('Rebuild Index')
    expect(html).toContain('Department Context')
  })
})

