import { useRef, useState } from 'react'
import { ArrowLeft, Check, ChevronDown, ImagePlus, LockKeyhole, Loader2, Sparkles, UserRound } from 'lucide-react'
import type { CharacterLook } from '../lib/characterLookApi'
import type { CharacterLooksController } from '../hooks/useCharacterLooks'
import { buildStudioApiUrl } from '../lib/studioApi'

const secondaryButton = 'inline-flex items-center justify-center gap-2 rounded-md border border-white/20 px-3 py-2.5 text-xs font-medium text-zinc-200 hover:border-white/35 hover:bg-white/5 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:cursor-not-allowed disabled:opacity-40'

function ReferenceImage({ url, name, className = '' }: { url: string; name: string; className?: string }) {
  const [failed, setFailed] = useState(false)
  return failed ? <div className={`flex items-center justify-center p-4 text-center text-xs text-zinc-400 ${className}`}>Image unavailable. Choose another reference.</div>
    : <img src={/^https?:\/\//.test(url) ? url : buildStudioApiUrl(url)} alt={name} onError={() => setFailed(true)} className={className} />
}

function CastingOptions({ look, controller, selectedUrl, onSelect }: { look: CharacterLook; controller: CharacterLooksController; selectedUrl: string; onSelect: (url: string) => void }) {
  const [direction, setDirection] = useState('')
  const generations = look.casting_generations || []
  const latest = generations[0]
  const pending = generations.some((generation) => generation.status === 'queued' || generation.status === 'running')
  const generated = look.candidates.filter((candidate) => candidate.generation_id)
  const currentOptions = latest ? generated.filter((candidate) => candidate.generation_id === latest.id) : generated
  const previousOptions = latest ? generated.filter((candidate) => candidate.generation_id !== latest.id) : []
  const hasAppearance = Boolean(look.physical_description.trim() || look.visual_prompt_summary.trim())
  const renderOptions = (options: typeof generated, previous = false) => <div className={`grid grid-cols-3 gap-2 sm:gap-3 ${previous ? 'mt-3' : 'mt-4'}`}>{options.map((candidate, index) => {
    const selected = selectedUrl === candidate.image_url
    return <button key={candidate.image_url} type="button" disabled={controller.busy} onClick={() => onSelect(candidate.image_url)} aria-label={`Choose ${previous ? 'previous ' : ''}casting option ${index + 1} for ${look.name}`} aria-pressed={selected} className={`group min-w-0 overflow-hidden rounded border text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:opacity-40 ${selected ? 'border-amber-200 bg-amber-200/10' : 'border-white/15 bg-black/30 hover:border-white/40'}`}>
      <span className="relative block aspect-[3/4] overflow-hidden bg-black/40"><ReferenceImage url={candidate.image_url} name={`${look.name} casting option ${index + 1}`} className="h-full w-full object-cover" />{selected && <span className="absolute bottom-2 right-2 rounded bg-amber-200 p-1 text-zinc-950"><Check size={14} /></span>}</span>
      <span className="block px-2 py-2.5"><span className={`block text-xs font-medium ${selected ? 'text-amber-100' : 'text-zinc-200'}`}>{selected ? 'Selected' : `Option ${index + 1}`}</span>{candidate.matches_current_profile === false && <span className="mt-1 block text-[10px] leading-snug text-amber-100/90">Earlier profile · review again</span>}</span>
    </button>
  })}</div>

  return <section aria-label={`Casting options for ${look.name}`} className="mt-5 border-t border-white/10 pt-5">
    <div className="flex flex-wrap items-center justify-between gap-3"><div><h4 className="text-sm font-medium text-zinc-100">Find the face for this character.</h4><p className="mt-1 text-xs leading-relaxed text-zinc-400">Create three portraits from the saved profile, then choose one.</p></div></div>
    <details className="mt-3">
      <summary className="flex w-fit cursor-pointer list-none items-center gap-2 py-1 text-xs text-zinc-300">Casting direction <span className="text-zinc-500">· optional</span><ChevronDown size={13} /></summary>
      <label className="mt-3 block text-xs text-zinc-400" htmlFor={`casting-direction-${look.character_id}`}>Guide the next set<textarea id={`casting-direction-${look.character_id}`} value={direction} disabled={controller.busy || pending} onChange={(event) => setDirection(event.target.value)} maxLength={1200} rows={3} placeholder="For example: a more reserved expression, softer window light." className="mt-2 block w-full resize-y rounded border border-white/20 bg-black/30 px-3 py-2.5 text-sm leading-relaxed text-zinc-200 placeholder:text-zinc-600 focus-visible:outline-2 focus-visible:outline-amber-200 disabled:opacity-40" /></label>
      <p className="mt-2 text-xs leading-relaxed text-zinc-500">Each set creates new faces. To change physical traits, edit and save the profile first.</p>
    </details>
    <div className="mt-4"><button type="button" onClick={() => void controller.generate(look, direction.trim())} disabled={controller.busy || pending || !hasAppearance} className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-amber-200/60 bg-amber-200/10 px-4 py-3 text-sm font-medium text-amber-100 hover:border-amber-100 hover:bg-amber-200/15 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:cursor-not-allowed disabled:border-white/15 disabled:bg-white/5 disabled:text-zinc-500 sm:w-auto">{pending ? <Loader2 size={15} className="animate-spin" /> : <Sparkles size={15} />}{pending ? 'Creating casting options…' : generations.length ? 'Generate a new set' : 'Generate 3 casting options'}</button><p className="mt-2 text-[11px] leading-relaxed text-zinc-500">Uses connected image provider credits. Your saved profile stays unchanged.</p></div>
    {!hasAppearance && <p className="mt-3 text-xs leading-relaxed text-amber-100">Save an appearance description in Character profiles first.</p>}
    {pending && <p role="status" className="mt-4 text-xs leading-relaxed text-zinc-300">{latest?.completed_count || 0} of {latest?.requested_count || 3} portraits ready. You can leave this page and return.</p>}
    {latest && (latest.status === 'partial' || latest.status === 'failed') && <div role="status" className="mt-4 border-l-2 border-amber-200/40 pl-3"><p className="text-xs leading-relaxed text-zinc-300">{latest.status === 'partial' ? `${latest.completed_count} of ${latest.requested_count} portraits were saved. You can choose one or generate a new set.` : 'This set could not be completed. Generate a new set when you’re ready.'}</p>{latest.error && <p className="mt-1 text-xs leading-relaxed text-zinc-400">{latest.error}</p>}</div>}
    {currentOptions.length > 0 && <>{renderOptions(currentOptions)}<p className="mt-3 text-xs leading-relaxed text-zinc-400">Choose a portrait to review it. Nothing is locked until you approve.</p></>}
    {previousOptions.length > 0 && <details className="mt-4"><summary className="flex w-fit cursor-pointer list-none items-center gap-2 py-1 text-xs text-zinc-300">Previous casting options <span className="text-zinc-500">· {previousOptions.length}</span><ChevronDown size={13} /></summary>{renderOptions(previousOptions, true)}</details>}
  </section>
}

function LookReview({ look, controller, onProfiles }: { look: CharacterLook; controller: CharacterLooksController; onProfiles: () => void }) {
  const [faceUrl, setFaceUrl] = useState(look.face_image_url || '')
  const [bodyUrl, setBodyUrl] = useState(look.body_image_url || '')
  const [uploadError, setUploadError] = useState('')
  const [confirmRevision, setConfirmRevision] = useState(false)
  const faceInput = useRef<HTMLInputElement>(null)
  const bodyInput = useRef<HTMLInputElement>(null)
  const locked = look.status === 'locked'
  const existingCandidates = look.candidates.filter((candidate) => !candidate.generation_id)
  const selectedCandidate = look.candidates.find((candidate) => candidate.image_url === faceUrl)
  const upload = async (file: File | undefined, role: 'face' | 'body') => {
    if (!file) return
    setUploadError('')
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 10 * 1024 * 1024) {
      setUploadError('Choose a JPEG, PNG, or WebP image up to 10 MB.')
      return
    }
    const imageUrl = await controller.upload(look, file)
    if (imageUrl) (role === 'face' ? setFaceUrl : setBodyUrl)(imageUrl)
  }

  return (
    <article className="overflow-hidden rounded-lg border border-white/10 bg-zinc-950/85">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4 sm:px-6">
        <div><p className="text-[10px] uppercase tracking-[0.18em] text-zinc-500">Character identity</p><h3 className="mt-1 text-xl font-medium text-zinc-100">{look.name}</h3></div>
        <span className={`inline-flex items-center gap-2 text-xs ${locked ? 'text-amber-100' : 'text-zinc-400'}`}>{locked ? <LockKeyhole size={14} /> : <span className="h-1.5 w-1.5 rounded-full bg-zinc-500" />}{locked ? `Look locked · version ${look.version}` : look.version ? `Revision draft · after version ${look.version}` : 'Draft · awaiting your approval'}</span>
      </header>
      <div className="grid min-w-0 gap-6 p-5 sm:p-6 lg:grid-cols-[minmax(240px,340px)_minmax(0,1fr)] lg:gap-9">
        <div className="min-w-0 lg:order-2">
          <p className="text-[11px] font-medium uppercase tracking-[0.15em] text-amber-100/80">{locked ? 'Approved physical identity' : 'Review the saved physical identity'}</p>
          <p className="mt-3 max-w-xl text-sm leading-relaxed text-zinc-400">Keep the face, build, skin tone, and age consistent. Costumes, styling, and injuries can change with the scene.</p>
          <dl className="mt-6 space-y-5">
            {look.age && <div><dt className="text-xs text-zinc-500">Age</dt><dd className="mt-1 text-sm text-zinc-200">{look.age}</dd></div>}
            <div><dt className="text-xs text-zinc-500">Physical appearance</dt><dd className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">{look.physical_description || 'No physical description saved yet.'}</dd></div>
            {look.visual_prompt_summary && look.visual_prompt_summary !== look.physical_description && <div><dt className="sr-only">Render description</dt><dd><details><summary className="flex w-fit cursor-pointer list-none items-center gap-2 text-xs text-zinc-400">Render description<ChevronDown size={13} /></summary><p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-zinc-300">{look.visual_prompt_summary}</p></details></dd></div>}
          </dl>
          {!locked && <button type="button" onClick={onProfiles} disabled={controller.busy} className="mt-4 inline-flex items-center gap-1.5 py-2 text-xs text-zinc-300 underline decoration-white/25 underline-offset-4 hover:text-amber-100 disabled:opacity-40"><ArrowLeft size={12} />Edit saved profile</button>}
          {!locked && <CastingOptions look={look} controller={controller} selectedUrl={faceUrl} onSelect={setFaceUrl} />}
          {!locked && existingCandidates.length > 0 && <details className="mt-5 border-t border-white/10 pt-4">
            <summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-zinc-300">Choose an existing reference<ChevronDown size={13} /></summary>
            <p className="mt-2 text-xs leading-relaxed text-zinc-500">Uploads and captured frames are candidates until you approve them.</p>
            <div className="mt-3 flex flex-wrap gap-2">{existingCandidates.map((candidate, index) => <button key={`${candidate.image_url}-${index}`} type="button" disabled={controller.busy} onClick={() => setFaceUrl(candidate.image_url)} aria-label={`Use reference ${index + 1} as ${look.name} portrait`} aria-pressed={faceUrl === candidate.image_url} className={`relative h-24 w-20 overflow-hidden rounded border focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:opacity-40 ${faceUrl === candidate.image_url ? 'border-amber-200' : 'border-white/15 hover:border-white/40'}`}><ReferenceImage url={candidate.image_url} name={`${look.name} reference ${index + 1}`} className="h-full w-full object-cover" />{faceUrl === candidate.image_url && <span className="absolute bottom-1 right-1 rounded bg-zinc-950 p-1 text-amber-200"><Check size={12} /></span>}</button>)}</div>
          </details>}
          <details className="mt-5 border-t border-white/10 pt-4">
            <summary className="flex cursor-pointer list-none items-center gap-2 text-xs text-zinc-300">Full-body reference <span className="text-zinc-500">· {bodyUrl ? 'added' : 'optional'}</span><ChevronDown size={13} /></summary>
            <p className="mt-2 text-xs leading-relaxed text-zinc-500">Support a consistent build and silhouette with a clear full-body image.</p>
            {bodyUrl && <ReferenceImage key={bodyUrl} url={bodyUrl} name={`${look.name} full-body reference`} className="mt-3 max-h-64 max-w-full rounded border border-white/10 object-contain" />}
            {!locked && <div className="mt-3 flex flex-wrap gap-2">
              <input ref={bodyInput} aria-label={`Upload ${look.name} full-body reference`} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(event) => { void upload(event.target.files?.[0], 'body'); event.target.value = '' }} />
              <button type="button" onClick={() => bodyInput.current?.click()} disabled={controller.busy} className={secondaryButton}><ImagePlus size={14} />{bodyUrl ? 'Change full-body image' : 'Upload full-body image'}</button>
              {bodyUrl && <button type="button" disabled={controller.busy} onClick={() => setBodyUrl('')} className={secondaryButton}>Remove selection</button>}
              {look.candidates.length > 0 && <label className="block w-full text-xs text-zinc-400">Or choose an existing image<select aria-label={`${look.name} full-body candidate`} value={look.candidates.some((candidate) => candidate.image_url === bodyUrl) ? bodyUrl : ''} disabled={controller.busy} onChange={(event) => setBodyUrl(event.target.value)} className="mt-2 block w-full max-w-sm rounded border border-white/15 bg-zinc-950 px-3 py-2 text-zinc-200"><option value="">Choose a reference</option>{look.candidates.map((candidate, index) => <option key={`${candidate.image_url}-${index}`} value={candidate.image_url}>Reference {index + 1} · {candidate.role.replaceAll('_', ' ')}</option>)}</select></label>}
            </div>}
          </details>
          {uploadError && <p role="alert" className="mt-4 text-sm text-rose-200">{uploadError}</p>}
        </div>
        <div className="min-w-0 lg:order-1">
          <div className={`relative flex w-full items-center justify-center overflow-hidden rounded border border-white/10 bg-black/50 ${faceUrl ? 'aspect-[4/5] max-h-[425px]' : 'h-44 lg:aspect-[4/5] lg:h-auto lg:max-h-[425px]'}`}>
            {faceUrl ? <ReferenceImage key={faceUrl} url={faceUrl} name={`${look.name} identity portrait`} className="h-full w-full object-contain" /> : <div className="flex max-w-[220px] flex-col items-center px-5 text-center"><UserRound size={42} strokeWidth={1} className="text-zinc-600" /><p className="mt-5 text-sm text-zinc-300">Choose {look.name}’s face.</p><p className="mt-2 text-xs leading-relaxed text-zinc-500">Generate casting options or upload a clear portrait.</p></div>}
          </div>
          <p className="mt-3 text-xs leading-relaxed text-zinc-400">{locked ? 'Your approved identity portrait.' : faceUrl ? 'Portrait selected. It becomes approved when you lock this look.' : 'A face reference is required to lock the look.'}</p>
          {!locked && selectedCandidate?.matches_current_profile === false && <p className="mt-2 text-xs leading-relaxed text-amber-100">This portrait came from an earlier profile. Review it against the saved appearance before locking.</p>}
          {!locked && <div className="mt-4">
            <input ref={faceInput} aria-label={`Upload ${look.name} face reference`} type="file" accept="image/jpeg,image/png,image/webp" className="hidden" onChange={(event) => { void upload(event.target.files?.[0], 'face'); event.target.value = '' }} />
            <button type="button" disabled={controller.busy} onClick={() => faceInput.current?.click()} className={`${secondaryButton} w-full`}><ImagePlus size={15} />{faceUrl ? 'Change portrait' : 'Upload portrait'}</button>
            <p className="mt-2 text-center text-[11px] text-zinc-500">JPEG, PNG, or WebP · up to 10 MB</p>
          </div>}
        </div>
      </div>
      <div className="border-t border-white/10 px-5 py-5 sm:px-6">
            {locked ? <>
              <p className="text-sm leading-relaxed text-zinc-300">This appearance is protected for future production.</p>
              {confirmRevision ? <div className="mt-3 rounded border border-amber-200/25 bg-amber-200/5 p-4"><p className="text-xs leading-relaxed text-zinc-300">Reopen this look to change its image or description. Approve it again before using the new look. Existing storyboards and footage stay unchanged.</p><div className="mt-3 flex flex-wrap gap-2"><button type="button" disabled={controller.busy} onClick={() => void controller.revise(look)} className={secondaryButton}>Reopen for revision</button><button type="button" disabled={controller.busy} onClick={() => setConfirmRevision(false)} className={secondaryButton}>Keep locked</button></div></div> : <button type="button" disabled={controller.busy} onClick={() => setConfirmRevision(true)} className={`mt-4 ${secondaryButton}`}>Revise look</button>}
            </> : <>
              <p className="mb-3 text-xs leading-relaxed text-zinc-400">Lock the saved description and chosen references together. You can deliberately revise them later.</p>
              <button type="button" onClick={() => void controller.approve(look, faceUrl, bodyUrl || null)} disabled={controller.busy || !faceUrl || !(look.physical_description.trim() || look.visual_prompt_summary.trim())} className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-amber-200 px-4 py-3 text-sm font-medium text-zinc-950 hover:bg-amber-100 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-amber-200 disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-zinc-500 sm:w-auto">{controller.busy ? <Loader2 size={15} className="animate-spin" /> : <LockKeyhole size={15} />}{controller.busy ? 'Saving…' : 'Approve and lock look'}</button>
              {!(look.physical_description.trim() || look.visual_prompt_summary.trim()) && <p className="mt-2 text-xs text-amber-100">Save an appearance description in Character profiles first.</p>}
            </>}
      </div>
    </article>
  )
}

export default function CharacterLookApproval({ controller, selectedId, onSelect, onProfiles, hasProfileDrafts }: {
  controller: CharacterLooksController
  selectedId: string
  onSelect: (id: string) => void
  onProfiles: () => void
  hasProfileDrafts: boolean
}) {
  const selected = controller.looks.find((look) => look.character_id === selectedId) || controller.looks[0]
  const lockedCount = controller.looks.filter((look) => look.status === 'locked').length
  return (
    <section aria-label="Lock character looks" className="space-y-5">
      <div><h2 className="text-lg font-medium text-zinc-100">Decide who we see on screen.</h2><p className="mt-1 max-w-2xl text-sm leading-relaxed text-zinc-400">Generate casting options or bring your own portrait. Choose and lock each character’s physical identity before storyboarding.</p></div>
      {hasProfileDrafts ? <div className="rounded-lg border border-amber-200/25 bg-zinc-950/80 p-5"><p className="text-sm text-amber-100">Save the character profile changes first.</p><p className="mt-2 text-xs text-zinc-400">Casting and approval use the saved appearance. Your unsaved drafts are still in Character profiles.</p><button type="button" onClick={onProfiles} className={`mt-4 ${secondaryButton}`}>Return to character profiles</button></div> : <>
        {controller.error && <div role="alert" className="rounded-md border border-rose-300/25 bg-rose-950/20 p-4"><p className="text-sm text-rose-200">{controller.error}</p><button type="button" onClick={() => void controller.refresh()} disabled={controller.busy} className="mt-2 text-xs text-zinc-200 underline underline-offset-4">Reload saved looks</button></div>}
        {controller.loading ? <p role="status" className="flex items-center gap-2 py-12 text-sm text-zinc-400"><Loader2 size={16} className="animate-spin" />Loading saved character looks…</p> : !selected ? !controller.error && <div className="rounded-lg border border-dashed border-white/15 bg-zinc-950/70 p-8"><UserRound size={25} className="text-zinc-500" /><h3 className="mt-4 text-base text-zinc-200">Start with a character profile.</h3><p className="mt-2 max-w-lg text-sm leading-relaxed text-zinc-400">Add characters from your script and save their appearance, then return here to choose their portraits.</p><button type="button" onClick={onProfiles} className={`mt-5 ${secondaryButton}`}>Open character profiles</button></div> : <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex min-w-0 flex-wrap items-center gap-3 text-xs text-zinc-400">Character<select aria-label="Character to approve" value={selected.character_id} disabled={controller.busy} onChange={(event) => onSelect(event.target.value)} className="max-w-full rounded-md border border-white/20 bg-zinc-950 px-3 py-2.5 text-sm text-zinc-200 focus-visible:outline-2 focus-visible:outline-amber-200">{controller.looks.map((look) => <option key={look.character_id} value={look.character_id}>{look.name} · {look.status === 'locked' ? 'locked' : 'needs approval'}</option>)}</select></label>
            <p className="text-xs text-zinc-500">{lockedCount} of {controller.looks.length} character looks locked</p>
          </div>
          <LookReview key={`${selected.character_id}:${selected.version}:${selected.status}`} look={selected} controller={controller} onProfiles={onProfiles} />
        </>}
      </>}
      <details className="max-w-3xl pt-2 text-xs text-zinc-400"><summary className="flex w-fit cursor-pointer list-none items-center gap-2 py-2 text-zinc-300">How the look carries into production<ChevronDown size={13} /></summary><div className="mt-2 space-y-2 leading-relaxed"><p>New storyboard prompts use the saved character description. The current storyboard image model works from text; supported video providers also receive your approved reference images.</p><p>Review every frame for likeness. A lock guides generation; it does not guarantee an identical face. After revising a look, regenerate the affected boards and takes yourself. Existing footage remains unchanged.</p></div></details>
    </section>
  )
}
