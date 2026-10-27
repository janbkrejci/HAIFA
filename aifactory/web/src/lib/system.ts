import { getGlobal, postGlobal } from './api'

export interface ResourceInfo {
  free: number | null
  total: number | null
  status: 'ok' | 'warning'
}

export interface SystemInfo {
  disk: ResourceInfo
  volumes: (ResourceInfo & { id: string; paths: string[] })[]
  memory: ResourceInfo
  status: 'ok' | 'warning'
}

export interface CleanupResult {
  advice_directories: string[]
  repos: { repo: string; removed: Record<string, unknown>[]; deleted_branches: string[]; warnings: string[] }[]
  freed_bytes: number | null
  warnings: string[]
}

export function fetchSystemInfo(): Promise<SystemInfo> {
  return getGlobal<SystemInfo>('/machine/system')
}

export function runCleanup(): Promise<CleanupResult> {
  return postGlobal<CleanupResult>('/machine/cleanup', {})
}
