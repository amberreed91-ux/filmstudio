import type { GateTone } from '../components/status/gateTones'
import type { BoardAsset } from './referenceBoardApi'

/** True for files kept on this machine (never http/data URLs). */
export function isLocalBoardFile(imageUrl: string | null | undefined): boolean {
  const url = (imageUrl || '').trim()
  if (!url) return true
  if (/^https?:\/\//i.test(url)) return false
  if (url.startsWith('data:')) return false
  return true
}

export type BoardCardState = { chip: string; tone: GateTone; reason: string }

/** Plain-language card state. Jargon stays in the details drawer. */
export function boardCardState(asset: BoardAsset): BoardCardState {
  const approved = asset.approval_state === 'approved'
  if (asset.canonical && approved) {
    return { chip: 'Settled', tone: 'ok', reason: 'This is the settled look. Keep using it.' }
  }
  if (asset.canonical) {
    return { chip: 'Needs a look', tone: 'waiting', reason: 'This settled choice needs a look before use.' }
  }
  if (approved) {
    return { chip: 'Supports the story', tone: 'ok', reason: 'Approved support. It does not replace the settled choice.' }
  }
  return { chip: 'Needs a look', tone: 'waiting', reason: 'Waiting ones need a yes.' }
}
