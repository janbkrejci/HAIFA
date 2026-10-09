<script setup lang="ts">
import { reactive } from 'vue'
import DiffContent from './DiffContent.vue'
import DetailSection from '@/components/runs/DetailSection.vue'
import { type DiffStatus, type ReviewDiff } from '@/lib/review'

defineProps<{ diff: ReviewDiff }>()

const STATUS: Record<DiffStatus, string> = {
  added: 'přidán',
  modified: 'změněn',
  deleted: 'smazán',
  renamed: 'přejmenován',
}

// Every file starts collapsed; the parent re-keys this view per PR.
const open = reactive<Record<string, boolean>>({})
</script>

<template>
  <div class="diff">
    <p class="stat" data-test="diff-stat">
      {{ diff.stat.files }} souborů ·
      <span class="add">+{{ diff.stat.additions }}</span>
      <span class="del">−{{ diff.stat.deletions }}</span>
      <span class="faint"> · proti {{ diff.base }}</span>
    </p>
    <p v-if="!diff.files.length" class="faint" data-test="no-diff">Žádné změny</p>
    <DetailSection
      v-for="f in diff.files"
      :key="f.path"
      :title="f.old_path ? `${f.old_path} → ${f.path}` : f.path"
      :open="!!open[f.path]"
      data-test="diff-file-section"
      :data-path="f.path"
      @toggle="open[f.path] = !open[f.path]"
    >
      <div class="file" data-test="diff-file" :data-path="f.path">
        <p class="file-head">
          <span class="status" :class="f.status">{{ STATUS[f.status] ?? f.status }}</span>
          <span class="add">+{{ f.additions }}</span>
          <span class="del">−{{ f.deletions }}</span>
          <span v-if="f.truncated" class="warn" data-test="truncated">diff zkrácen</span>
        </p>
        <DiffContent :binary="f.binary" :patch="f.patch" />
      </div>
    </DetailSection>
  </div>
</template>

<style scoped>
.stat {
  margin: 0 0 10px;
}

.add {
  color: var(--green);
  font-family: var(--mono);
  margin-right: 6px;
}

.del {
  color: var(--red);
  font-family: var(--mono);
  margin-right: 6px;
}

.file-head {
  display: flex;
  gap: 8px;
  align-items: baseline;
  margin: 0 0 6px;
}

.status {
  font-size: 13px;
  color: var(--dim);
}

.status.added {
  color: var(--green);
}

.status.deleted {
  color: var(--red);
}

.warn {
  color: var(--amber);
}

.patch {
  margin: 0;
  padding: 8px 0;
  overflow-x: auto;
  background: var(--panel-3);
  border: 1px solid var(--border-soft);
  border-radius: 6px;
  font-family: var(--mono);
  font-size: 13px;
}

.line {
  display: block;
  padding: 0 10px;
  white-space: pre;
}

.line.add {
  margin: 0;
  background: rgba(74, 222, 128, 0.1);
}

.line.del {
  margin: 0;
  background: rgba(255, 111, 103, 0.1);
}

.line.hunk {
  color: var(--cyan);
}

.line.meta {
  color: var(--faint);
}
</style>
