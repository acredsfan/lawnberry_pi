// Lightweight performance metrics collection for Task 7
// Captures hydration time, WebSocket ready time, and custom marks.
// Designed to be Pi-friendly: minimal overhead, conditional logging.

export interface PerfMetricsSnapshot {
  navigationStart?: number
  domContentLoaded?: number
  hydrationComplete?: number
  hydrationDurationMs?: number
  webSocketConnected?: number
  webSocketConnectDurationMs?: number
  customMarks: Record<string, number>
  exportedAt: number
}

class PerfMetricsCollector {
  private marks: Map<string, number> = new Map()
  private wsConnectStart?: number
  private wsConnectedAt?: number
  private hydrationAt?: number
  private exported = false

  mark(name: string): void {
    if (!this.marks.has(name)) {
      this.marks.set(name, performance.now())
    }
  }

  setHydrationComplete(): void {
    if (!this.hydrationAt) {
      this.hydrationAt = performance.now()
      this.mark('hydration_complete')
    }
  }

  setWebSocketConnectStart(): void {
    if (!this.wsConnectStart) {
      this.wsConnectStart = performance.now()
    }
  }

  setWebSocketConnected(): void {
    if (!this.wsConnectedAt) {
      this.wsConnectedAt = performance.now()
      this.mark('ws_connected')
    }
  }

  exportSnapshot(): PerfMetricsSnapshot {
    if (this.exported) {
      // allow multiple exports but only first includes base nav timings
    }
    const navStart = performance.timing?.navigationStart
    const dcl = performance.timing?.domContentLoadedEventEnd
    const snapshot: PerfMetricsSnapshot = {
      navigationStart: navStart,
      domContentLoaded: dcl,
      hydrationComplete: this.hydrationAt,
      hydrationDurationMs: this.hydrationAt && navStart ? this.hydrationAt - navStart : undefined,
      webSocketConnected: this.wsConnectedAt,
      webSocketConnectDurationMs: this.wsConnectStart && this.wsConnectedAt ? this.wsConnectedAt - this.wsConnectStart : undefined,
      customMarks: Object.fromEntries(this.marks.entries()),
      exportedAt: Date.now(),
    }
    this.exported = true
    return snapshot
  }
}

export const perfMetrics = new PerfMetricsCollector()

// Expose globally (debug)
if (typeof window !== 'undefined') {
  ;(window as any).lawnPerf = perfMetrics
}
