/**
 * AudioGenerationPanel
 *
 * Per-scene audio generation UI for the Previs Room.
 * Shows three track status indicators (Dialogue / Score / Ambient),
 * a "Generate Audio" button, per-track regenerate buttons, and
 * HTML5 audio players when tracks are complete.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import {
  generateSceneAudio,
  getSceneAudioStatus,
  type AudioJobResult,
  type TrackResult,
  type TrackStatus,
} from '../lib/audioApi'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SoundAdvisory {
  mood?: string
  score_notes?: string
  ambient_notes?: string
  silence_flag?: boolean
}

interface AudioGenerationPanelProps {
  projectId: string
  sceneId: string
  soundAdvisory?: SoundAdvisory
  sceneDescription?: string
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const TRACK_LABELS: Record<string, string> = {
  dialogue: 'Dialogue',
  score: 'Score',
  ambient: 'Ambient',
}

const TRACK_ICONS: Record<string, string> = {
  dialogue: '🎙',
  score: '🎼',
  ambient: '🌆',
}

function statusColor(status: TrackStatus | undefined): string {
  switch (status) {
    case 'complete': return 'text-emerald-300'
    case 'generating': return 'text-amber-300'
    case 'failed': return 'text-rose-300'
    case 'skipped': return 'text-zinc-400'
    case 'mock': return 'text-cyan-300'
    default: return 'text-zinc-500'
  }
}

function statusDot(status: TrackStatus | undefined): string {
  switch (status) {
    case 'complete': return 'bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.6)]'
    case 'generating': return 'bg-amber-400 animate-pulse'
    case 'failed': return 'bg-rose-400'
    case 'skipped': return 'bg-zinc-500'
    case 'mock': return 'bg-cyan-400'
    default: return 'bg-zinc-600'
  }
}

function statusLabel(status: TrackStatus | undefined): string {
  switch (status) {
    case 'complete': return 'Complete'
    case 'generating': return 'Generating…'
    case 'failed': return 'Failed'
    case 'skipped': return 'Silence'
    case 'mock': return 'Mock'
    default: return 'Pending'
  }
}

// ---------------------------------------------------------------------------
// TrackCard sub-component
// ---------------------------------------------------------------------------

interface TrackCardProps {
  trackKey: 'dialogue' | 'score' | 'ambient'
  result: TrackResult | undefined
  onRegenerate: (track: 'dialogue' | 'score' | 'ambient') => void
  regenerating: boolean
}

function TrackCard({ trackKey, result, onRegenerate, regenerating }: TrackCardProps) {
  const audioRef = useRef<HTMLAudioElement>(null)
  const status = result?.status
  const fileUrl = result?.file_url
  const isComplete = status === 'complete' || status === 'mock'

  return (
    <div className="rounded-lg border border-zinc-700/60 bg-zinc-900/70 p-3 space-y-2">
      {/* Header row */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-base">{TRACK_ICONS[trackKey]}</span>
          <span className="text-[11px] font-semibold uppercase tracking-[0.13em] text-zinc-200">
            {TRACK_LABELS[trackKey]}
          </span>
        </div>
        <div className="flex items-center gap-2">
          {/* Status dot + label */}
          <div className={`h-2 w-2 rounded-full ${statusDot(status)}`} />
          <span className={`text-[10px] font-medium ${statusColor(status)}`}>
            {statusLabel(status)}
          </span>
          {/* Regenerate button */}
          <button
            type="button"
            onClick={() => onRegenerate(trackKey)}
            disabled={regenerating}
            className="rounded border border-zinc-600/50 bg-zinc-800/60 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-[0.12em] text-zinc-300 hover:border-cyan-400/50 hover:text-cyan-200 disabled:cursor-not-allowed disabled:opacity-40 transition-colors"
          >
            {regenerating ? '…' : '↺'}
          </button>
        </div>
      </div>

      {/* Advisory / prompt */}
      {result?.advisory && (
        <p className="text-[10px] text-zinc-400 leading-relaxed">{result.advisory}</p>
      )}
      {result?.prompt_used && (
        <p className="text-[10px] text-zinc-500 italic truncate" title={result.prompt_used}>
          Prompt: {result.prompt_used}
        </p>
      )}
      {result?.text_used && (
        <p className="text-[10px] text-zinc-500 italic truncate" title={result.text_used}>
          Text: "{result.text_used}"
        </p>
      )}
      {result?.error && (
        <p className="text-[10px] text-rose-300">{result.error}</p>
      )}

      {/* Audio player */}
      {isComplete && fileUrl && (
        <div className="pt-1">
          <audio
            ref={audioRef}
            controls
            src={fileUrl}
            className="w-full h-8"
            style={{ colorScheme: 'dark' }}
          />
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export default function AudioGenerationPanel({
  projectId,
  sceneId,
  soundAdvisory,
  sceneDescription,
}: AudioGenerationPanelProps) {
  const [job, setJob] = useState<AudioJobResult | null>(null)
  const [generating, setGenerating] = useState(false)
  const [regeneratingTrack, setRegeneratingTrack] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Load existing status on mount
  useEffect(() => {
    if (!projectId || !sceneId) return
    getSceneAudioStatus(projectId, sceneId)
      .then(setJob)
      .catch(() => {/* no status yet — that's fine */})
  }, [projectId, sceneId])

  // Poll while generating
  useEffect(() => {
    if (!generating) {
      if (pollRef.current) clearInterval(pollRef.current)
      return
    }
    pollRef.current = setInterval(async () => {
      try {
        const status = await getSceneAudioStatus(projectId, sceneId)
        setJob(status)
        if (status.status === 'complete' || status.status === 'failed') {
          setGenerating(false)
        }
      } catch {
        // ignore poll errors
      }
    }, 3000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [generating, projectId, sceneId])

  const handleGenerateAll = useCallback(async () => {
    if (!projectId || !sceneId) return
    setGenerating(true)
    setError(null)
    try {
      const result = await generateSceneAudio(projectId, sceneId, {
        scene_description: sceneDescription,
        mood: soundAdvisory?.mood,
        score_notes: soundAdvisory?.score_notes,
        ambient_notes: soundAdvisory?.ambient_notes,
        silence_flag: soundAdvisory?.silence_flag,
      })
      setJob(result)
      if (result.status === 'complete' || result.status === 'failed') {
        setGenerating(false)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Generation failed')
      setGenerating(false)
    }
  }, [projectId, sceneId, sceneDescription, soundAdvisory])

  const handleRegenerateTrack = useCallback(
    async (track: 'dialogue' | 'score' | 'ambient') => {
      if (!projectId || !sceneId) return
      setRegeneratingTrack(track)
      setError(null)
      try {
        const result = await generateSceneAudio(projectId, sceneId, {
          track,
          scene_description: sceneDescription,
          mood: soundAdvisory?.mood,
          score_notes: soundAdvisory?.score_notes,
          ambient_notes: soundAdvisory?.ambient_notes,
          silence_flag: soundAdvisory?.silence_flag,
        })
        // Merge the single track result into existing job
        setJob((prev) => {
          if (!prev) return result
          return {
            ...prev,
            tracks: {
              ...prev.tracks,
              ...result.tracks,
            },
          }
        })
      } catch (err) {
        setError(err instanceof Error ? err.message : `Failed to regenerate ${track}`)
      } finally {
        setRegeneratingTrack(null)
      }
    },
    [projectId, sceneId, sceneDescription, soundAdvisory],
  )

  const isMock = job?.mock_mode === true
  const tracks = job?.tracks ?? {}

  return (
    <div className="rounded-xl border border-zinc-700/50 bg-zinc-900/80 p-4 space-y-3">
      {/* Panel header */}
      <div className="flex items-center justify-between gap-3">
        <div>
          <h4 className="text-[11px] font-semibold uppercase tracking-[0.14em] text-zinc-200">
            🎧 Audio Generation
          </h4>
          {isMock && (
            <p className="mt-0.5 text-[9px] text-cyan-300 uppercase tracking-[0.1em]">
              Mock mode — models not installed
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={handleGenerateAll}
          disabled={generating}
          className="rounded-lg border border-cyan-400/40 bg-cyan-500/15 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-[0.13em] text-cyan-100 hover:bg-cyan-500/25 hover:border-cyan-300/60 disabled:cursor-not-allowed disabled:opacity-50 transition-all"
        >
          {generating ? 'Generating…' : 'Generate Audio'}
        </button>
      </div>

      {/* Sound advisory summary */}
      {soundAdvisory && (
        <div className="rounded-lg border border-zinc-700/40 bg-zinc-800/40 px-3 py-2 space-y-0.5">
          {soundAdvisory.mood && (
            <p className="text-[10px] text-zinc-300">
              <span className="text-zinc-500">Mood:</span> {soundAdvisory.mood}
            </p>
          )}
          {soundAdvisory.score_notes && (
            <p className="text-[10px] text-zinc-300">
              <span className="text-zinc-500">Score:</span> {soundAdvisory.score_notes}
            </p>
          )}
          {soundAdvisory.ambient_notes && (
            <p className="text-[10px] text-zinc-300">
              <span className="text-zinc-500">Ambient:</span> {soundAdvisory.ambient_notes}
            </p>
          )}
          {soundAdvisory.silence_flag && (
            <p className="text-[10px] text-amber-300">⚠ Silence flag — intentional silence</p>
          )}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-[10px] text-rose-300">
          {error}
        </div>
      )}

      {/* Job advisory */}
      {job?.advisory && !error && (
        <p className="text-[10px] text-zinc-400">{job.advisory}</p>
      )}

      {/* Track cards */}
      <div className="space-y-2">
        {(['dialogue', 'score', 'ambient'] as const).map((trackKey) => (
          <TrackCard
            key={trackKey}
            trackKey={trackKey}
            result={tracks[trackKey]}
            onRegenerate={handleRegenerateTrack}
            regenerating={regeneratingTrack === trackKey}
          />
        ))}
      </div>
    </div>
  )
}
