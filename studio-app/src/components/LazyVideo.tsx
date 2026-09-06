import { useState, useRef, useEffect, type ReactNode } from 'react'

interface LazyVideoProps {
  src: string
  poster?: string
  className?: string
  preload?: 'none' | 'metadata' | 'auto'
  fallback?: ReactNode
  onLoad?: () => void
  onError?: (error: Error) => void
}

export function LazyVideo({ 
  src, 
  poster, 
  className = '', 
  preload = 'none',
  fallback,
  onLoad,
  onError 
}: LazyVideoProps) {
  const [isInView, setIsInView] = useState(false)
  const [isLoaded, setIsLoaded] = useState(false)
  const [hasError, setHasError] = useState(false)
  const videoRef = useRef<HTMLVideoElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsInView(true)
          observer.disconnect()
        }
      },
      { rootMargin: '50px' }
    )

    observer.observe(container)

    return () => observer.disconnect()
  }, [])

  useEffect(() => {
    if (!isInView || !videoRef.current) return

    const video = videoRef.current
    
    const handleLoad = () => {
      setIsLoaded(true)
      onLoad?.()
    }

    const handleError = () => {
      setHasError(true)
      const error = new Error('Video failed to load')
      onError?.(error)
    }

    video.addEventListener('loadeddata', handleLoad)
    video.addEventListener('error', handleError)

    // Start loading the video when in view
    video.load()

    return () => {
      video.removeEventListener('loadeddata', handleLoad)
      video.removeEventListener('error', handleError)
    }
  }, [isInView, onLoad, onError])

  if (hasError && fallback) {
    return <>{fallback}</>
  }

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {!isLoaded && (
        <div className="absolute inset-0 flex items-center justify-center bg-zinc-800/50">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-amber-400"></div>
        </div>
      )}
      
      {isInView ? (
        <video
          ref={videoRef}
          src={src}
          poster={poster}
          preload={preload}
          className={`w-full h-full object-cover ${isLoaded ? 'opacity-100' : 'opacity-0'} transition-opacity duration-300`}
          controls
          playsInline
        />
      ) : (
        <div className="w-full h-full bg-zinc-800/50 flex items-center justify-center">
          <div className="text-zinc-400 text-sm">Video will load when visible</div>
        </div>
      )}
    </div>
  )
}

// Optimized video player for render previews
interface RenderVideoProps {
  outputUrl?: string
  previewUrl?: string
  className?: string
  showControls?: boolean
}

export function RenderVideo({ 
  outputUrl, 
  previewUrl, 
  className = '',
  showControls = true
}: RenderVideoProps) {
  if (!outputUrl && !previewUrl) {
    return (
      <div className={`w-full h-full bg-zinc-800/50 flex items-center justify-center ${className}`}>
        <div className="text-zinc-400 text-sm">No video available</div>
      </div>
    )
  }

  // Use preview URL for faster loading if available, otherwise use output URL
  const videoSrc = previewUrl || outputUrl

  if (!videoSrc) {
    return (
      <div className={`w-full h-full bg-zinc-800/50 flex items-center justify-center ${className}`}>
        <div className="text-zinc-400 text-sm">No video source available</div>
      </div>
    )
  }

  return (
    <div className={`relative ${className}`}>
      <LazyVideo
        src={videoSrc}
        className="w-full h-full"
        preload="metadata"
        onError={(error) => console.error('Video load error:', error)}
      />
      
      {showControls && (
        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-2">
          <div className="flex items-center gap-2 text-white text-xs">
            <span>Video Preview</span>
          </div>
        </div>
      )}
    </div>
  )
}
