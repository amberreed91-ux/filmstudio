import type { ReactNode } from 'react'

/**
 * Jargon lives here and only here. Digests, fingerprints, studio roles,
 * manifests, and other machine evidence stay inside this drawer — never in
 * chips, reasons, or next-action lines.
 */
export default function TechDetailsDrawer({
  summary = 'Why (technical details)',
  children,
  className = 'mt-2 text-xs text-zinc-400',
}: {
  summary?: string
  children: ReactNode
  className?: string
}) {
  return (
    <details className={className}>
      <summary className="cursor-pointer text-amber-200/90">{summary}</summary>
      <div className="mt-1">{children}</div>
    </details>
  )
}

export function BlockerList({ items }: { items: string[] }) {
  return (
    <ul className="list-disc space-y-1 pl-5">
      {items.map((item) => (
        <li key={item}>{item}</li>
      ))}
    </ul>
  )
}
