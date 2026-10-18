import { useState, type ReactNode } from 'react'
import { useStudioSession } from '../hooks/useStudioSession'

export function StudioSessionGate({ children }: { children: ReactNode }) {
  const { status, error, diagnostic, busy, signIn, retrySessionCheck } = useStudioSession()
  const diagnosticMessage = diagnostic
    ? `${diagnostic.stage === 'session' ? 'Session' : 'Access-mode'} check failed: ${diagnostic.kind === 'network' ? 'connection failure' : `HTTP ${diagnostic.status}`}`
    : ''
  const [register, setRegister] = useState(false)
  if (status === 'ready') return children
  if (status === 'checking') return <div className="p-12 text-zinc-300" role="status">Checking your studio session…</div>
  if (status === 'unavailable') return <main className="min-h-screen bg-zinc-950 text-zinc-100 grid place-items-center p-6">
    <section className="w-full max-w-sm space-y-5" aria-labelledby="backend-unavailable-title">
      <h1 id="backend-unavailable-title" className="text-3xl font-medium">Studio temporarily unavailable</h1>
      <p role="alert" className="text-zinc-300">{error}</p>
      {diagnosticMessage && <p className="text-sm text-zinc-400" data-testid="studio-session-diagnostic">{diagnosticMessage}</p>}
      <button type="button" onClick={retrySessionCheck} className="w-full rounded bg-amber-200 p-3 text-zinc-950">Check connection again</button>
    </section>
  </main>
  return <main className="min-h-screen bg-zinc-950 text-zinc-100 grid place-items-center p-6">
    <form className="w-full max-w-sm space-y-5" onSubmit={event => {
      event.preventDefault()
      const values = new FormData(event.currentTarget)
      void signIn(String(values.get('username')), String(values.get('password')), register ? String(values.get('email')) : undefined)
    }}>
      <h1 className="text-3xl font-medium">{register ? 'Create your studio account' : 'Sign in to your studio'}</h1>
      <p className="text-zinc-400">Your films and production materials stay in your account.</p>
      <label className="block">Username<input name="username" autoComplete="username" required className="mt-2 w-full rounded border border-zinc-700 bg-zinc-900 p-3" /></label>
      {register && <label className="block">Email<input name="email" type="email" autoComplete="email" required className="mt-2 w-full rounded border border-zinc-700 bg-zinc-900 p-3" /></label>}
      <label className="block">Password<input name="password" type="password" autoComplete={register ? 'new-password' : 'current-password'} required className="mt-2 w-full rounded border border-zinc-700 bg-zinc-900 p-3" /></label>
      {error && <p role="alert" className="text-red-300">{error}</p>}
      <button disabled={busy} className="w-full rounded bg-amber-200 p-3 text-zinc-950 disabled:opacity-50">{busy ? 'Opening…' : register ? 'Create account' : 'Sign in'}</button>
      <button type="button" className="text-sm text-zinc-300 underline" onClick={() => setRegister(!register)}>{register ? 'Use an existing account' : 'Create an account'}</button>
    </form>
  </main>
}
