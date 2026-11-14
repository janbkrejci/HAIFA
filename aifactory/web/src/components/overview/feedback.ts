/** The outcome of a factory button (RepoActions), shown under the buttons by RepoControls. */
export interface ControlFeedback {
  message: string | (() => string) | null
  error: string | (() => string) | null
  diagnostics?: string
}

export const NO_FEEDBACK: ControlFeedback = { message: null, error: null }

export function feedbackText(value: string | (() => string) | null): string {
  return typeof value === 'function' ? value() : value ?? ''
}
