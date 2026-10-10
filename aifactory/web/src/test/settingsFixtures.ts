import type { ConfigStatus, SettingsData } from '@/lib/settings'

export const SETTINGS: SettingsData = {
  shared: {
    workdir: '.',
    backlog_dir: 'backlog',
    specs_dir: 'specs',
    docs_dir: 'app_docs',
    worktrees_dir: '.factory/worktrees',
    base: 'main',
    git_provider: 'local',
    merge_strategy: 'squash',
    protected_files: ['.factory/'],
    max_parallel_runs: 1,
  },
  local: { trace_db: '.factory/trace.db' },
  files: { shared: '.factory/config.yaml', local: '.factory/local.yaml' },
  options: { git_provider: ['local', 'github', 'azure'], merge_strategy: ['squash', 'merge'] },
  shared_issues: [],
  local_issues: [],
  status: null,
}

export const DIRTY_STATUS: ConfigStatus = {
  base: 'main',
  commit: 'abcdef1234567890',
  clean: false,
  changes: [
    { path: '.factory/config.yaml', status: 'modified' },
    { path: '.factory/workflows/new.yaml', status: 'untracked' },
  ],
}

export const CLEAN_STATUS: ConfigStatus = {
  base: 'main',
  commit: 'abcdef1234567890',
  clean: true,
  changes: [],
}
