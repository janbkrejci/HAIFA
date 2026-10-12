import type { ConfigStatus, SettingsData } from '@/lib/settings'

export const SETTINGS: SettingsData = {
  shared: {
    workdir: '.',
    docs_root: 'factory',
    worktrees_dir: '.factory/worktrees',
    base: 'main',
    git_provider: 'local',
    merge_strategy: 'squash',
    base_changes: 'direct',
    base_pr_merge: 'manual',
    protected_files: ['.factory/'],
    max_parallel_runs: 1,
  },
  local: { trace_db: '.factory/trace.db' },
  files: { shared: '.factory/config.yaml', local: '.factory/local.yaml' },
  options: { git_provider: ['local', 'github', 'azure'], merge_strategy: ['squash', 'merge'], base_changes: ['direct', 'pr'], base_pr_merge: ['manual', 'auto'] },
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
