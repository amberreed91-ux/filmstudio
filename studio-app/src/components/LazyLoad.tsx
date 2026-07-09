import { Suspense, lazy, type ReactNode, useState, useEffect, useRef } from 'react'

interface LazyLoadProps {
  children: ReactNode
  fallback?: ReactNode
  delay?: number
  rootMargin?: string
  threshold?: number
}

// Generic lazy loading wrapper
export function LazyLoad({ 
  children, 
  fallback = <div className="animate-pulse bg-zinc-800/50 h-32 rounded-lg" />,
  delay = 0
}: LazyLoadProps) {
  const [shouldLoad, setShouldLoad] = useState(delay === 0)

  useEffect(() => {
    if (delay === 0) return

    const timer = setTimeout(() => {
      setShouldLoad(true)
    }, delay)

    return () => clearTimeout(timer)
  }, [delay])

  if (!shouldLoad) {
    return <>{fallback}</>
  }

  return (
    <Suspense fallback={fallback}>
      {children}
    </Suspense>
  )
}

// Intersection Observer based lazy loading
export function LazyLoadOnVisible({ 
  children, 
  fallback = <div className="animate-pulse bg-zinc-800/50 h-32 rounded-lg" />,
  rootMargin = '50px',
  threshold = 0.1
}: Omit<LazyLoadProps, 'delay'>) {
  const [hasBeenVisible, setHasBeenVisible] = useState(false)
  const elementRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = elementRef.current
    if (!element) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setHasBeenVisible(true)
        }
      },
      { rootMargin, threshold }
    )

    observer.observe(element)

    return () => {
      observer.unobserve(element)
    }
  }, [rootMargin, threshold])

  if (!hasBeenVisible) {
    return <div ref={elementRef}>{fallback}</div>
  }

  return (
    <div ref={elementRef}>
      <Suspense fallback={fallback}>
        {children}
      </Suspense>
    </div>
  )
}

// Higher-order component for lazy loading any component
export function lazyLoad<T extends React.ComponentType<any>>(
  componentFactory: () => Promise<{ default: T }>,
  fallback?: ReactNode
) {
  const LazyComponent = lazy(componentFactory)
  
  return function LazyLoadedComponent(props: React.ComponentProps<T>) {
    return (
      <Suspense fallback={fallback || <div className="animate-pulse bg-zinc-800/50 h-32 rounded-lg" />}>
        <LazyComponent {...props} />
      </Suspense>
    )
  }
}

// Hook for lazy loading state
export function useLazyLoad(delay = 0) {
  const [shouldLoad, setShouldLoad] = useState(delay === 0)

  useEffect(() => {
    if (delay === 0) return

    const timer = setTimeout(() => {
      setShouldLoad(true)
    }, delay)

    return () => clearTimeout(timer)
  }, [delay])

  return shouldLoad
}
