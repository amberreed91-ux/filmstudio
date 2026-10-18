import { describe, expect, it } from 'vitest';
import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import type { ComponentProps } from 'react';
import ShotIntentRationaleCard from './ShotIntentRationaleCard';
import PrevisCinematicShowcase from './PrevisCinematicShowcase';
import ScreeningCinematicShowcase from './ScreeningCinematicShowcase';

function previsProps(overrides: Partial<ComponentProps<typeof PrevisCinematicShowcase>> = {}) {
  return {
    projectId: 'demo_studio_cinematic_001',
    sceneId: 'scene_001',
    sceneTitle: 'INT. HALLWAY - NIGHT',
    cinematicIntent: 'Build dread through narrowed framing.',
    emotionalBeat: 'Suspicion rising',
    referenceConfidenceLabel: 'Reference-linked',
    currentStatus: 'complete',
    hasDirectorSignature: true,
    relatedMemoryCount: 3,
    continuityIssueCount: 0,
    styleDriftIssueCount: 0,
    visualEvidenceCount: 3,
    decisionGateStatus: 'ready',
    isDemoProject: true,
    ...overrides,
  } as ComponentProps<typeof PrevisCinematicShowcase>;
}

function screeningProps(overrides: Partial<ComponentProps<typeof ScreeningCinematicShowcase>> = {}) {
  return {
    projectId: 'demo_studio_cinematic_001',
    projectTitle: 'Demo Project',
    heroPreviewUrl: '',
    heroVideoUrl: '',
    activeSceneId: 'scene_001',
    gateStatus: 'ready',
    decisionGate: null,
    renderStatusLabel: 'COMFYUI RENDER',
    runtimeEstimateLabel: '3 min',
    revisionCount: 1,
    renderJobsCount: 1,
    reviewsCount: 1,
    packagesCount: 1,
    continuityIssuesCount: 0,
    styleDriftIssuesCount: 0,
    memoryRecordsCount: 3,
    hasDirectorSignature: true,
    revisions: [{ id: 'a', label: 'Revision A', status: 'completed', runtimeSeconds: 12 }],
    onApproveCut: () => {},
    onRequestRevision: () => {},
    onCompareRevision: () => {},
    onExportPackage: () => {},
    ...overrides,
  } as ComponentProps<typeof ScreeningCinematicShowcase>;
}

describe('ShotIntentRationaleCard', () => {
  it('renders explicit intent without throwing on full shot', () => {
    const html = renderToStaticMarkup(
      <ShotIntentRationaleCard
        shot={{ intent: 'Holds on Maya as the room goes quiet.' }}
        testId="why-this-shot-matters-previs"
      />,
    );
    expect(html).toContain('why-this-shot-matters-previs');
    expect(html).toContain('Why this shot matters');
    expect(html).toContain('Holds on Maya as the room goes quiet.');
  });

  it('renders fallback cleanly for null shot', () => {
    const html = renderToStaticMarkup(
      <ShotIntentRationaleCard shot={null} testId="why-this-shot-matters-screening" />,
    );
    expect(html).toContain('why-this-shot-matters-screening');
    expect(html).toContain('Establishes key visual beats and emotional tone');
  });
});

describe('why-this-shot-matters surfaces', () => {
  it('renders rationale card in Previs view', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <PrevisCinematicShowcase
          {...previsProps({ shot: { director_notes: 'Let silence hurt as much as dialogue' } })}
        />
      </MemoryRouter>,
    );
    expect(html).toContain('why-this-shot-matters-previs');
    expect(html).toContain('Let silence hurt as much as dialogue.');
  });

  it('renders rationale card in Screening view', () => {
    const html = renderToStaticMarkup(
      <MemoryRouter>
        <ScreeningCinematicShowcase
          {...screeningProps({ shot: { prompt: 'Low-angle push-in through smoke' } })}
        />
      </MemoryRouter>,
    );
    expect(html).toContain('why-this-shot-matters-screening');
    expect(html).toContain('Why this shot matters');
  });
});
