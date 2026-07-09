import { describe, it, expect } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { PitchDeckSection } from './PitchDeckSection';

describe('PitchDeckSection', () => {
  it('renders pitch deck section', () => {
    const html = renderToStaticMarkup(<PitchDeckSection projectId="project_123" />);
    expect(html).toContain('Pitch Deck');
  });

  it('renders generate draft button', () => {
    const html = renderToStaticMarkup(<PitchDeckSection projectId="project_123" />);
    expect(html).toContain('Generate Draft');
  });

  it('renders empty state when no decks', () => {
    const html = renderToStaticMarkup(<PitchDeckSection projectId="project_123" />);
    expect(html).toContain('No pitch decks yet');
  });

  it('uses purple color for generate button', () => {
    const html = renderToStaticMarkup(<PitchDeckSection projectId="project_123" />);
    expect(html).toContain('bg-purple-600');
  });
});
