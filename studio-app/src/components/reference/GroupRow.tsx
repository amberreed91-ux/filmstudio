import type { ReactNode } from 'react'

export default function GroupRow({
  title,
  count,
  children,
}: {
  title: string
  count: number
  children: ReactNode
}) {
  return (
    <section aria-label={title} className="mt-6">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-200/80">
        {title} · {count}
      </h2>
      <div className="mt-2 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{children}</div>
    </section>
  )
}
