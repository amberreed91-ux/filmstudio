import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import VoicePicker from './VoicePicker'

const defaultProps = {
  isOpen: true,
  onClose: () => {},
  projectId: 'proj-test',
  characterId: 'char-1',
  characterName: 'MARA',
  currentVoiceId: null,
  currentVoiceName: null,
  onAssigned: () => {},
}

describe('VoicePicker', () => {
  it('renders nothing when isOpen is false', () => {
    const html = renderToStaticMarkup(
      <VoicePicker {...defaultProps} isOpen={false} />,
    )
    expect(html).toBe('')
  })

  it('renders the character name in the header', () => {
    const html = renderToStaticMarkup(
      <VoicePicker {...defaultProps} characterName="ELI" />,
    )
    expect(html).toContain('ELI')
    expect(html).toContain('Voice Casting')
  })

  it('renders search input', () => {
    const html = renderToStaticMarkup(
      <VoicePicker {...defaultProps} />,
    )
    expect(html).toContain('Search voices by name')
  })

  it('renders gender, age, and accent filter dropdowns', () => {
    const html = renderToStaticMarkup(
      <VoicePicker {...defaultProps} />,
    )
    expect(html).toContain('All Genders')
    expect(html).toContain('All Ages')
    expect(html).toContain('All Accents')
  })

  it('renders Done button', () => {
    const html = renderToStaticMarkup(
      <VoicePicker {...defaultProps} />,
    )
    expect(html).toContain('Done')
  })

  it('shows current voice assignment when one exists', () => {
    const html = renderToStaticMarkup(
      <VoicePicker
        {...defaultProps}
        currentVoiceId="v123"
        currentVoiceName="Rachel"
      />,
    )
    expect(html).toContain('Assigned')
    expect(html).toContain('Rachel')
  })

  it('shows Clear button when voice is assigned', () => {
    const html = renderToStaticMarkup(
      <VoicePicker
        {...defaultProps}
        currentVoiceId="v123"
        currentVoiceName="Rachel"
      />,
    )
    expect(html).toContain('Clear')
  })

  it('shows empty state message when no voices loaded', () => {
    const html = renderToStaticMarkup(
      <VoicePicker {...defaultProps} />,
    )
    expect(html).toContain('No voices available')
  })

  it('has the voice-picker-modal test id', () => {
    const html = renderToStaticMarkup(
      <VoicePicker {...defaultProps} />,
    )
    expect(html).toContain('voice-picker-modal')
  })
})
