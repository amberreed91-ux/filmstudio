/**
 * Centralized localStorage API with shared constants and schema management.
 * Replaces scattered localStorage.getItem/setItem calls across the codebase.
 */

export const STORAGE_KEYS = {
  ACTIVE_PROJECT_ID: "studio:active-project-id",
  SELECTED_PROJECT_ID: "studio:selected-project-id",
  LAST_BUNDLE: "studio:lastBundle",
  LAST_SCRIPT: "studio:lastScript",
  FILM_CUT: "studio:filmCut",
  APPROVED_SCENES: "studio:approvedScenes",
  SCENE_REVIEW_STATUS: "studio:sceneReviewStatus",
  ONBOARDING_DISMISSED: "studio:onboarding:dismissed",
  DEV_MODE: "devMode",
  CREW_EXPANDED: "studio:crewExpanded",
  COST_SETTINGS: "studio:COST_SETTINGS",
  AGENT_ACTIVITY: "studio:agentActivity",
  LAST_SHORT_FILM_WORKFLOW: "studio:lastShortFilmWorkflow",
} as const;

export type StorageKey = (typeof STORAGE_KEYS)[keyof typeof STORAGE_KEYS];

function safeGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function safeSet(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // localStorage full or unavailable — silently fail
  }
}

function safeRemove(key: string): void {
  try {
    localStorage.removeItem(key);
  } catch {
    // Silently fail
  }
}

// Typed accessors
export function getActiveProjectId(): string | null {
  return safeGet(STORAGE_KEYS.ACTIVE_PROJECT_ID);
}

export function setActiveProjectId(id: string | null): void {
  if (id) {
    safeSet(STORAGE_KEYS.ACTIVE_PROJECT_ID, id);
  } else {
    safeRemove(STORAGE_KEYS.ACTIVE_PROJECT_ID);
  }
}

export function getSelectedProjectId(): string | null {
  return safeGet(STORAGE_KEYS.SELECTED_PROJECT_ID);
}

export function setSelectedProjectId(id: string | null): void {
  if (id) {
    safeSet(STORAGE_KEYS.SELECTED_PROJECT_ID, id);
  } else {
    safeRemove(STORAGE_KEYS.SELECTED_PROJECT_ID);
  }
}

export function getDevMode(): boolean {
  return safeGet(STORAGE_KEYS.DEV_MODE) === "true";
}

export function setDevMode(enabled: boolean): void {
  safeSet(STORAGE_KEYS.DEV_MODE, String(enabled));
}

export function getOnboardingDismissed(): boolean {
  return safeGet(STORAGE_KEYS.ONBOARDING_DISMISSED) === "true";
}

export function setOnboardingDismissed(dismissed: boolean): void {
  safeSet(STORAGE_KEYS.ONBOARDING_DISMISSED, String(dismissed));
}

/**
 * Remove stale localStorage keys that are no longer in the known set.
 * Called once on app initialization.
 */
export function cleanupStaleStorage(): void {
  const KNOWN_KEYS = new Set<string>(Object.values(STORAGE_KEYS));
  const keysToRemove: string[] = [];

  for (let i = localStorage.length - 1; i >= 0; i--) {
    const key = localStorage.key(i);
    if (key && key.startsWith("studio:") && !KNOWN_KEYS.has(key)) {
      keysToRemove.push(key);
    }
  }

  keysToRemove.forEach((key) => safeRemove(key));
}
