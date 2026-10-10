import type { FactoryInitPlan, FactoryCheck } from '@/lib/api'

export function factoryCheck(): FactoryCheck {
  return { in_repo: true, repo: '/work/HAIFA', state: 'installed', action: null, onboarding: null,
    base: 'main', commit: 'abcdef123', remote: 'origin', ahead: 0, behind: 0, offline: false, ok: true, counts: { error: 0, warning: 0, info: 0 }, findings: [], checked_at: '2026-10-07T10:00:00Z', cached: false, manifest: { format: 1, written_by: 'test' }, manifest_error: null, version: 'test' }
}

export function installPlan(extra: Partial<FactoryInitPlan> = {}): FactoryInitPlan {
  const agents = ['planner', 'builder', 'reviewer', 'documenter']
  const binding = { harness: 'claude', model: 'sonnet', thinking: 'medium' }
  return {
    action: 'init', base: 'main', base_sha: 'abcdef123', remote: 'origin', digest: 'install-digest', blockers: [],
    files: [{ path: '.factory/manifest.yaml', action: 'create', content: 'format: 1\n', diff: '', binary: false }],
    provider: 'local', backlog_dir: 'backlog', specs_dir: 'specs', docs_dir: 'docs', agents, workflows: ['simple-sdlc'], added_agents: [],
    bindings: Object.fromEntries(agents.map(name => [name, { ...binding }])),
    available: { agents: [...agents, 'scout'].map(name => ({ name, purpose: name, default: name !== 'scout', ...binding })), workflows: [{ name: 'simple-sdlc', default: true }, { name: 'scout', default: false }] },
    detected: { harnesses: { claude: { installed: true }, codex: { installed: false }, pi: { installed: true } } },
    ...extra,
  }
}
