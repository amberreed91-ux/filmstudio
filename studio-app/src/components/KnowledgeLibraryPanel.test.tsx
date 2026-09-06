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
  uploadKnowledgeBible: vi.fn(),
}))

describe('KnowledgeLibraryPanel', () => {
  it('renders project Bibles with optional knowledge tools', () => {
    const html = renderToStaticMarkup(<KnowledgeLibraryPanel projectId="project-knowledge" />)

    expect(html).toContain('Project Bibles')
    expect(html).toContain('Add Bible')
    expect(html).toContain('Upload Markdown Bible')
    expect(html).toContain('Rebuild Index')
    expect(html).toContain('Department Context')
  })
})
