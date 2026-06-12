/**
 * Taste Memory v1 - Frontend Session Only
 * 
 * Track filmmaker preferences from repeated choices — slowly, softly, reversibly.
 * Following AGENTS.md Taste Memory Rules:
 * - Infer from revision emphasis toggle behavior only
 * - Track one axis: emotional_residue_vs_structural_clarity
 * - Use tendency language only: "you tend to..." never "you always..."
 * - Confidence labels: emerging/consistent/strong — no percentages
 * - One event never defines taste — patterns over time define advisory tendencies
 * - Never block workflow actions
 */

import { useCallback, useEffect, useRef, useState } from 'react'

type TasteAxis = 'emotional_residue' | 'structural_clarity'

type TasteConfidence = 'emerging' | 'consistent' | 'strong'

type TasteObservation = {
  timestamp: number
  selectedAxis: TasteAxis
  context: 'revision_emphasis_toggle' | 'comparison_behavior'
}

type TasteMemory = {
  observations: TasteObservation[]
  currentLeaning: TasteAxis | null
  confidence: TasteConfidence
  observationCount: number
  sessionStartTime: number
}

// Confidence thresholds (based on observation count and consistency)
const CONFIDENCE_THRESHOLDS = {
  emerging: 2,    // At least 2 observations to show emerging
  consistent: 4,  // At least 4 observations to show consistent
  strong: 7,      // At least 7 observations to show strong
}

// Consistency ratio required (how many times the same choice was made)
const CONSISTENCY_RATIO = {
  emerging: 0.6,   // 60% of observations on same axis
  consistent: 0.7, // 70% of observations on same axis
  strong: 0.8,     // 80% of observations on same axis
}

function calculateTasteConfidence(
  observations: TasteObservation[],
  dominantAxis: TasteAxis,
): TasteConfidence {
  const total = observations.length
  const dominantCount = observations.filter(obs => obs.selectedAxis === dominantAxis).length
  const ratio = dominantCount / total

  if (total >= CONFIDENCE_THRESHOLDS.strong && ratio >= CONSISTENCY_RATIO.strong) {
    return 'strong'
  }
  if (total >= CONFIDENCE_THRESHOLDS.consistent && ratio >= CONSISTENCY_RATIO.consistent) {
    return 'consistent'
  }
  if (total >= CONFIDENCE_THRESHOLDS.emerging && ratio >= CONSISTENCY_RATIO.emerging) {
    return 'emerging'
  }
  return 'emerging' // Default to emerging if we have any observations
}

function getTendencyLanguage(
  leaning: TasteAxis | null,
  confidence: TasteConfidence,
  observationCount: number,
): string {
  if (!leaning || observationCount < CONFIDENCE_THRESHOLDS.emerging) {
    return 'The Studio is still observing your creative choices to understand your tendencies.'
  }

  const axisLabel = leaning === 'emotional_residue' ? 'emotional residue' : 'structural clarity'

  if (confidence === 'strong') {
    return `Across this session, you tend to favor ${axisLabel} when refining cuts.`
  }
  if (confidence === 'consistent') {
    return `You tend to lean toward ${axisLabel} in revision decisions.`
  }
  // emerging
  return `Early signs suggest you may lean toward ${axisLabel}, though more choices are needed to confirm.`
}

export function useTasteMemory() {
  const [memory, setMemory] = useState<TasteMemory>(() => ({
    observations: [],
    currentLeaning: null,
    confidence: 'emerging',
    observationCount: 0,
    sessionStartTime: Date.now(),
  }))

  // Debounce observations to avoid over-counting rapid toggles
  const lastObservationTime = useRef<number>(0)
  const OBSERVATION_DEBOUNCE_MS = 2000 // Don't count observations within 2 seconds of each other

  const recordObservation = useCallback((axis: TasteAxis, context: TasteObservation['context']) => {
    const now = Date.now()
    
    // Debounce: ignore if too soon after last observation
    if (now - lastObservationTime.current < OBSERVATION_DEBOUNCE_MS) {
      return
    }
    
    lastObservationTime.current = now

    setMemory(prev => {
      const newObservation: TasteObservation = {
        timestamp: now,
        selectedAxis: axis,
        context,
      }

      const updatedObservations = [...prev.observations, newObservation]

      // Calculate which axis is dominant
      const emotionalCount = updatedObservations.filter(obs => obs.selectedAxis === 'emotional_residue').length
      const structuralCount = updatedObservations.filter(obs => obs.selectedAxis === 'structural_clarity').length

      let dominantAxis: TasteAxis | null = null
      if (emotionalCount > structuralCount) {
        dominantAxis = 'emotional_residue'
      } else if (structuralCount > emotionalCount) {
        dominantAxis = 'structural_clarity'
      }

      // Calculate confidence if we have a dominant axis
      const confidence = dominantAxis
        ? calculateTasteConfidence(updatedObservations, dominantAxis)
        : 'emerging'

      return {
        observations: updatedObservations,
        currentLeaning: dominantAxis,
        confidence,
        observationCount: updatedObservations.length,
        sessionStartTime: prev.sessionStartTime,
      }
    })
  }, [])

  const clearMemory = useCallback(() => {
    setMemory({
      observations: [],
      currentLeaning: null,
      confidence: 'emerging',
      observationCount: 0,
      sessionStartTime: Date.now(),
    })
    lastObservationTime.current = 0
  }, [])

  const getTendencyMessage = useCallback(() => {
    return getTendencyLanguage(memory.currentLeaning, memory.confidence, memory.observationCount)
  }, [memory.currentLeaning, memory.confidence, memory.observationCount])

  const getConfidenceLabel = useCallback((): TasteConfidence => {
    return memory.confidence
  }, [memory.confidence])

  const getCurrentLeaning = useCallback((): TasteAxis | null => {
    return memory.currentLeaning
  }, [memory.currentLeaning])

  const getObservationCount = useCallback((): number => {
    return memory.observationCount
  }, [memory.observationCount])

  const hasEnoughData = useCallback((): boolean => {
    return memory.observationCount >= CONFIDENCE_THRESHOLDS.emerging
  }, [memory.observationCount])

  const getTasteState = useCallback(() => {
    return {
      currentLeaning: memory.currentLeaning,
      confidence: memory.confidence,
      observationCount: memory.observationCount,
      hasEnoughData: memory.observationCount >= CONFIDENCE_THRESHOLDS.emerging,
    }
  }, [memory.currentLeaning, memory.confidence, memory.observationCount])

  return {
    // State
    currentLeaning: memory.currentLeaning,
    confidence: memory.confidence,
    observationCount: memory.observationCount,
    
    // Actions
    recordObservation,
    clearMemory,
    
    // Helpers
    getTendencyMessage,
    getConfidenceLabel,
    getCurrentLeaning,
    getObservationCount,
    hasEnoughData,
    getTasteState,
  }
}
