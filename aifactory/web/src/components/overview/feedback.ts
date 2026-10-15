/** The outcome of a factory button (RepoActions), shown under the buttons by RepoControls. */
export interface ControlFeedback {
  message: string | null
  error: string | null
}

export const NO_FEEDBACK: ControlFeedback = { message: null, error: null }
