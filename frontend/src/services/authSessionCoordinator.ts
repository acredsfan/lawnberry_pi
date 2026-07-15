type RefreshHandler = () => Promise<string | null>
type ClearHandler = () => void

let refreshHandler: RefreshHandler | null = null
let clearHandler: ClearHandler | null = null

/** Register the active Pinia auth store as the single token-state owner. */
export function registerAuthSessionCoordinator(
  refresh: RefreshHandler,
  clear: ClearHandler,
): void {
  refreshHandler = refresh
  clearHandler = clear
}

/** Refresh through the active store so reactive state and storage stay aligned. */
export async function refreshAuthenticatedSession(): Promise<string | null> {
  return refreshHandler ? refreshHandler() : null
}

/** Clear through the active store after an unrecoverable authentication error. */
export function clearAuthenticatedSession(): void {
  clearHandler?.()
}
