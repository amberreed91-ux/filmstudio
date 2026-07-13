import { useCallback, useEffect, useRef, useState } from 'react'
import {
  Check,
  Loader2,
  Pause,
  Play,
  Search,
  Volume2,
  X,
} from 'lucide-react'
import {
  listElevenLabsVoices,
  setCharacterVoice,
  type ElevenLabsVoice,
} from '../lib/studioApi'

type VoicePickerProps = {
  isOpen: boolean
  onClose: () => void
  projectId: string
  characterId: string
  characterName: string
  currentVoiceId: string | null
  currentVoiceName: string | null
  onAssigned: (voiceId: string, voiceName: string) => void
}

const GENDER_OPTIONS = ['', 'male', 'female']
const AGE_OPTIONS = ['', 'young', 'middle aged', 'old']
const ACCENT_OPTIONS = ['', 'american', 'british', 'african', 'indian', 'australian']

export default function VoicePicker({
  isOpen,
  onClose,
  projectId,
  characterId,
  characterName,
  currentVoiceId,
  currentVoiceName,
  onAssigned,
}: VoicePickerProps) {
  const [voices, setVoices] = useState<ElevenLabsVoice[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [genderFilter, setGenderFilter] = useState('')
  const [ageFilter, setAgeFilter] = useState('')
  const [accentFilter, setAccentFilter] = useState('')
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [assigningId, setAssigningId] = useState<string | null>(null)
  const [assignedId, setAssignedId] = useState<string | null>(currentVoiceId)

  const audioRef = useRef<HTMLAudioElement | null>(null)

  const loadVoices = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const { voices: fetched, error: fetchError } = await listElevenLabsVoices(projectId)
      if (fetchError) {
        setError(fetchError)
      } else {
        setVoices(fetched)
      }
    } catch {
      setError('Failed to load voices')
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    if (isOpen) {
      setAssignedId(currentVoiceId)
      void loadVoices()
    }
  }, [isOpen, currentVoiceId, loadVoices])

  useEffect(() => {
    return () => {
      if (audioRef.current) {
        audioRef.current.pause()
        audioRef.current = null
      }
    }
  }, [])

  const handlePlay = (voice: ElevenLabsVoice) => {
    if (!voice.preview_url) return
    if (playingId === voice.voice_id) {
      if (audioRef.current) {
        audioRef.current.pause()
        setPlayingId(null)
      }
      return
    }
    if (audioRef.current) {
      audioRef.current.pause()
    }
    const audio = new Audio(voice.preview_url)
    audio.onended = () => setPlayingId(null)
    audio.onerror = () => {
      setPlayingId(null)
      setError('Audio preview failed to play')
    }
    audioRef.current = audio
    void audio.play()
    setPlayingId(voice.voice_id)
  }

  const handleAssign = async (voice: ElevenLabsVoice) => {
    console.log('ASSIGN clicked', voice.voice_id, characterId)
    setAssigningId(voice.voice_id)
    setError('')
    try {
      const { error: assignError } = await setCharacterVoice(
        projectId,
        characterId,
        voice.voice_id,
        voice.name,
      )
      if (assignError) {
        setError(assignError)
      } else {
        setAssignedId(voice.voice_id)
        onAssigned(voice.voice_id, voice.name)
      }
    } catch {
      setError('Failed to assign voice')
    } finally {
      setAssigningId(null)
    }
  }

  const handleClear = async () => {
    setAssigningId('clear')
    setError('')
    try {
      const { error: clearError } = await setCharacterVoice(
        projectId,
        characterId,
        '',
        '',
      )
      if (clearError) {
        setError(clearError)
      } else {
        setAssignedId(null)
        onAssigned('', '')
      }
    } catch {
      setError('Failed to clear voice')
    } finally {
      setAssigningId(null)
    }
  }

  const filtered = voices.filter((v) => {
    if (searchQuery) {
      const q = searchQuery.toLowerCase()
      if (!v.name.toLowerCase().includes(q)) return false
    }
    if (genderFilter && v.labels.gender !== genderFilter) return false
    if (ageFilter && v.labels.age !== ageFilter) return false
    if (accentFilter && v.labels.accent !== accentFilter) return false
    return true
  })

  if (!isOpen) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
      onClick={onClose}
      data-testid="voice-picker-modal"
    >
      <div
        className="w-full max-w-2xl rounded-2xl border border-zinc-700/70 bg-gradient-to-br from-zinc-950 via-zinc-900 to-black p-6 shadow-[0_20px_60px_rgba(0,0,0,0.6)]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="mb-4 flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-[0.16em] text-cyan-200">
              Voice Casting
            </div>
            <h2 className="mt-1 text-xl font-semibold text-zinc-100">
              {characterName}
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-zinc-400 transition-colors hover:bg-white/10 hover:text-zinc-200"
          >
            <X size={18} />
          </button>
        </div>

        {/* Current assignment */}
        {assignedId && (
          <div className="mb-4 flex items-center justify-between rounded-lg border border-cyan-400/30 bg-cyan-500/8 px-3 py-2">
            <div className="flex items-center gap-2">
              <Volume2 size={14} className="text-cyan-300" />
              <span className="text-xs text-cyan-100">
                Assigned: <span className="font-semibold">{currentVoiceName || voices.find(v => v.voice_id === assignedId)?.name || 'Unknown'}</span>
              </span>
            </div>
            <button
              type="button"
              onClick={handleClear}
              disabled={assigningId !== null}
              className="rounded-md border border-rose-400/30 bg-rose-500/10 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-rose-200 transition-all hover:scale-[1.02] disabled:opacity-50"
            >
              {assigningId === 'clear' ? 'Clearing...' : 'Clear'}
            </button>
          </div>
        )}

        {/* Search + Filters */}
        <div className="mb-3 space-y-2">
          <div className="relative">
            <Search
              size={14}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500"
            />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search voices by name..."
              className="w-full rounded-md border border-zinc-700 bg-zinc-950/80 py-2 pl-9 pr-3 text-sm text-zinc-100 outline-none focus:border-cyan-400/50"
            />
          </div>
          <div className="flex flex-wrap gap-2">
            <select
              value={genderFilter}
              onChange={(e) => setGenderFilter(e.target.value)}
              className="rounded-md border border-zinc-700 bg-zinc-950/80 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-cyan-400/50"
            >
              {GENDER_OPTIONS.map((g) => (
                <option key={g} value={g} className="bg-zinc-900">
                  {g ? g.charAt(0).toUpperCase() + g.slice(1) : 'All Genders'}
                </option>
              ))}
            </select>
            <select
              value={ageFilter}
              onChange={(e) => setAgeFilter(e.target.value)}
              className="rounded-md border border-zinc-700 bg-zinc-950/80 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-cyan-400/50"
            >
              {AGE_OPTIONS.map((a) => (
                <option key={a} value={a} className="bg-zinc-900">
                  {a ? a.charAt(0).toUpperCase() + a.slice(1) : 'All Ages'}
                </option>
              ))}
            </select>
            <select
              value={accentFilter}
              onChange={(e) => setAccentFilter(e.target.value)}
              className="rounded-md border border-zinc-700 bg-zinc-950/80 px-2 py-1.5 text-[11px] text-zinc-200 outline-none focus:border-cyan-400/50"
            >
              {ACCENT_OPTIONS.map((a) => (
                <option key={a} value={a} className="bg-zinc-900">
                  {a ? a.charAt(0).toUpperCase() + a.slice(1) : 'All Accents'}
                </option>
              ))}
            </select>
            <div className="ml-auto text-[11px] text-zinc-500">
              {filtered.length} voice{filtered.length !== 1 ? 's' : ''}
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-3 rounded-md border border-rose-400/40 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
            {error}
          </div>
        )}

        {/* Voice list */}
        <div className="max-h-[400px] space-y-1.5 overflow-y-auto pr-1">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 size={20} className="animate-spin text-cyan-300" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <Volume2 size={24} className="mb-3 opacity-30 text-zinc-500" />
              <p className="text-xs text-zinc-500">
                {voices.length === 0 ? 'No voices available. Check API key configuration.' : 'No voices match your filters.'}
              </p>
            </div>
          ) : (
            filtered.map((voice) => {
              const isAssigned = assignedId === voice.voice_id
              const isPlaying = playingId === voice.voice_id
              const isAssigning = assigningId === voice.voice_id
              return (
                <div
                  key={voice.voice_id}
                  className={`flex items-center justify-between rounded-lg border px-3 py-2.5 transition-colors ${
                    isAssigned
                      ? 'border-cyan-400/40 bg-cyan-500/8'
                      : 'border-zinc-800 bg-zinc-900/40 hover:border-zinc-700'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    {/* Play button */}
                    <button
                      type="button"
                      onClick={() => handlePlay(voice)}
                      disabled={!voice.preview_url}
                      className="flex h-8 w-8 items-center justify-center rounded-full border border-zinc-600 bg-zinc-800/60 text-zinc-300 transition-all hover:scale-105 hover:border-cyan-400/50 hover:text-cyan-300 disabled:opacity-30"
                      title={voice.preview_url ? 'Preview' : 'No preview available'}
                    >
                      {isPlaying ? (
                        <Pause size={14} />
                      ) : (
                        <Play size={14} />
                      )}
                    </button>

                    {/* Voice info */}
                    <div>
                      <div className="text-sm font-medium text-zinc-100">
                        {voice.name}
                      </div>
                      <div className="flex flex-wrap gap-1.5 mt-0.5">
                        {voice.labels.gender && (
                          <span className="rounded-full border border-zinc-700 bg-zinc-800/60 px-2 py-0.5 text-[9px] uppercase tracking-[0.1em] text-zinc-400">
                            {voice.labels.gender}
                          </span>
                        )}
                        {voice.labels.age && (
                          <span className="rounded-full border border-zinc-700 bg-zinc-800/60 px-2 py-0.5 text-[9px] uppercase tracking-[0.1em] text-zinc-400">
                            {voice.labels.age}
                          </span>
                        )}
                        {voice.labels.accent && (
                          <span className="rounded-full border border-zinc-700 bg-zinc-800/60 px-2 py-0.5 text-[9px] uppercase tracking-[0.1em] text-zinc-400">
                            {voice.labels.accent}
                          </span>
                        )}
                        {voice.category && (
                          <span className="rounded-full border border-zinc-700 bg-zinc-800/60 px-2 py-0.5 text-[9px] uppercase tracking-[0.1em] text-zinc-500">
                            {voice.category}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Assign button */}
                  {isAssigned ? (
                    <div className="flex items-center gap-1.5 rounded-md border border-cyan-400/40 bg-cyan-500/14 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-cyan-200">
                      <Check size={12} />
                      Assigned
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => handleAssign(voice)}
                      disabled={isAssigning}
                      className="flex items-center gap-1.5 rounded-md border border-amber-400/30 bg-amber-500/12 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-200 transition-all hover:scale-[1.02] disabled:opacity-50"
                    >
                      {isAssigning === voice.voice_id ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Check size={12} />
                      )}
                      Assign
                    </button>
                  )}
                </div>
              )
            })
          )}
        </div>

        {/* Footer */}
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-zinc-600/80 bg-zinc-900/70 px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-zinc-200"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
