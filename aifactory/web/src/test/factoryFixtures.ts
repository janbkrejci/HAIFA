import type { FactoryInitPlan, FactoryCheck } from '@/lib/api'

export function factoryCheck(): FactoryCheck {
  return { in_repo: true, repo: '/work/HAIFA', state: 'installed', action: null,
    base: 'main', commit: 'abcdef123', remote: 'origin', ahead: 0, behind: 0, offline: false, ok: true, counts: { error: 0, warning: 0, info: 0 }, findings: [], checked_at: '2026-10-07T10:00:00Z', cached: false, version: 'test' }
}

export function installPlan(extra: Partial<FactoryInitPlan> = {}): FactoryInitPlan {
  return {
    action: 'init', base: 'main', base_sha: 'abcdef123', remote: 'origin', digest: 'install-digest', blockers: [],
    files: [{ path: '.factory/config.yaml', action: 'create', content: 'base: main\n', diff: '', binary: false }],
    provider: 'local', docs_root: 'factory',
    detected: { harnesses: { claude: { installed: true }, codex: { installed: false }, pi: { installed: true } } },
    ...extra,
  }
}
