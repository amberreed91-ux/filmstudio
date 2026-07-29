interface ErrorReport {
  error_id: string;
  timestamp: number;
  message: string;
  stack?: string;
  component_stack?: string;
  url: string;
  user_agent: string;
  build_version: string;
  level: "fatal" | "error" | "warning";
  context?: Record<string, unknown>;
}

const TELEMETRY_ENDPOINT = import.meta.env.VITE_ERROR_TELEMETRY_URL || "";
const BUILD_VERSION = import.meta.env.VITE_BUILD_VERSION || "dev";
const MAX_QUEUE_SIZE = 100;
const FLUSH_INTERVAL_MS = 5000;

let errorQueue: ErrorReport[] = [];
let flushTimer: ReturnType<typeof setInterval> | null = null;

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`
}

export function reportError(
  error: Error,
  componentStack?: string,
  level: ErrorReport["level"] = "error",
  context?: Record<string, unknown>
): void {
  const report: ErrorReport = {
    error_id: generateId(),
    timestamp: Date.now(),
    message: error.message,
    stack: error.stack,
    component_stack: componentStack,
    url: window.location.href,
    user_agent: navigator.userAgent,
    build_version: BUILD_VERSION,
    level,
    context,
  };

  if (!TELEMETRY_ENDPOINT) {
    if (import.meta.env.DEV) {
      console.warn("[ErrorTelemetry] No endpoint configured:", report);
    }
    return;
  }

  if (errorQueue.length >= MAX_QUEUE_SIZE) {
    errorQueue.shift();
  }

  errorQueue.push(report);

  if (!flushTimer) {
    flushTimer = setInterval(flushErrors, FLUSH_INTERVAL_MS);
  }

  if (errorQueue.length >= 10) {
    flushErrors();
  }
}

function flushErrors(): void {
  if (errorQueue.length === 0) return;

  const batch = [...errorQueue];
  errorQueue = [];

  if (flushTimer) {
    clearInterval(flushTimer);
    flushTimer = null;
  }

  fetch(`${TELEMETRY_ENDPOINT}/api/f51/studio/errors`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ errors: batch }),
    keepalive: true,
  }).catch(() => {
    // Telemetry failure should never break the app
  });
}
