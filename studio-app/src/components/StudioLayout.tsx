import type { ReactNode } from 'react'

interface StudioLayoutProps {
  children: ReactNode
  className?: string
}

export default function StudioLayout({ children, className = '' }: StudioLayoutProps) {
  return (
    <div className={`flex flex-col min-h-screen ${className}`}>
      {children}
    </div>
  )
}
