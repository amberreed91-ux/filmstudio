import { useState, type ReactNode } from 'react'
import { useStudioSession } from '../hooks/useStudioSession'

export function StudioSessionGate({ children }: { children: ReactNode }) {
  const { status, error, busy, signIn } = useStudioSession()
  const [register, setRegister] = useState(false)
  if (status === 'ready') return children
  if (status === 'loading') return <div className="p-12 text-zinc-300" role="status">Opening your studio…</div>
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
