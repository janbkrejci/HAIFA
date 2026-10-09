<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, shallowRef } from 'vue'
import type { SessionSummary } from '../lib/types'
import { archiveFinishedSessions, fetchSessions } from '../lib/api'
import { ts } from '../lib/format'
import SessionCard from './SessionCard.vue'

const sessions = shallowRef<SessionSummary[]>([])
const apiError = ref<string | null>(null)
const loaded = ref(false)
const nowMs = ref(Date.now())

let timer: ReturnType<typeof setInterval> | undefined
let inflight = false

async function tick() {
  if (inflight) return
  inflight = true
  try {
    sessions.value = await fetchSessions()
    nowMs.value = Date.now()
    apiError.value = null
    loaded.value = true
  } catch (err) {
    apiError.value = err instanceof Error ? err.message : String(err)
  } finally {
    inflight = false
  }
}

onMounted(() => {
  void tick()
  timer = setInterval(() => void tick(), 500)
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  clearInterval(timer)
  clearTimeout(toastTimer)
  window.removeEventListener('keydown', onKeydown)
})

const finishedCount = computed(() => sessions.value.filter((s) => s.status && s.status !== 'running').length)
const askingArchive = ref(false)
const archiving = ref(false)
const toast = ref<{ kind: 'ok' | 'err'; msg: string } | null>(null)
let toastTimer: ReturnType<typeof setTimeout> | undefined

function showToast(kind: 'ok' | 'err', msg: string) {
  clearTimeout(toastTimer)
  toast.value = { kind, msg }
  toastTimer = setTimeout(() => (toast.value = null), 3000)
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape' && askingArchive.value) askingArchive.value = false
}

/** The server decides what counts as finished, so the poll re-syncs the list after. */
async function confirmArchiveFinished() {
  askingArchive.value = false
  archiving.value = true
  try {
    const count = await archiveFinishedSessions()
    sessions.value = sessions.value.filter((s) => !s.status || s.status === 'running')
    showToast('ok', `Archived ${count} finished run${count === 1 ? '' : 's'}`)
  } catch {
    showToast('err', 'Failed to archive the finished runs')
    void tick()
  } finally {
    archiving.value = false
  }
}

/** Optimistic removal; an empty id means the write failed, so re-sync instead. */
function onArchived(adwId: string) {
  if (!adwId) {
    void tick()
    return
  }
  sessions.value = sessions.value.filter((s) => s.adw_id !== adwId)
}

const ordered = computed(() =>
  sessions.value.toSorted((a, b) => (ts(b.started_at) || 0) - (ts(a.started_at) || 0)),
)
</script>

<template>
  <div class="sessions">
    <div v-if="apiError" class="error-bar">api unreachable — retrying {{ apiError }}</div>

    <div v-if="toast" :class="['toast', toast.kind]">{{ toast.msg }}</div>

    <div v-if="ordered.length" class="list-head">
      <span class="dim">{{ ordered.length }} runs</span>
      <button
        v-if="finishedCount"
        class="archive-all-btn"
        type="button"
        :disabled="archiving"
        @click="askingArchive = true"
      >
        {{ archiving ? 'Archiving…' : `Archive all finished (${finishedCount})` }}
      </button>
    </div>

    <div v-if="ordered.length" class="cards">
      <SessionCard
        v-for="s in ordered"
        :key="s.adw_id"
        :session="s"
        :now-ms="nowMs"
        @archived="onArchived"
      />
    </div>
    <div v-else-if="loaded" class="empty-state">no sessions yet — run an ADW to see it here</div>
    <div v-else-if="!apiError" class="empty-state">loading sessions…</div>

    <Teleport to="body">
      <div v-if="askingArchive" class="aa-backdrop" @click="askingArchive = false">
        <div
          class="aa-dialog"
          role="alertdialog"
          aria-modal="true"
          aria-label="Archive all finished runs?"
          @click.stop
        >
          <div class="aa-title">Archive all {{ finishedCount }} finished runs?</div>
          <p class="aa-hint">
            Every run that is no longer running leaves the review list. Running runs stay.
            You can restore any of them from the archived view.
          </p>
          <div class="aa-actions">
            <button class="aa-act" type="button" @click="askingArchive = false">Cancel</button>
            <button class="aa-act aa-confirm" type="button" @click="confirmArchiveFinished">Archive</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.sessions {
  display: flex;
  flex-direction: column;
}

.list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 24px 0;
  font-size: 16px;
}

.archive-all-btn,
.aa-act {
  flex: none;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font-family: inherit;
  font-size: 15px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.archive-all-btn:hover,
.aa-act:hover {
  background: var(--panel-3);
}

.archive-all-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

/* Teleported to body, so it renders above everything; styles stay scoped here. */
.aa-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.55);
  backdrop-filter: blur(4px);
  -webkit-backdrop-filter: blur(4px);
}

.aa-dialog {
  width: min(460px, calc(100vw - 48px));
  padding: 24px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--surface);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.aa-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 12px;
}

.aa-hint {
  margin: 0 0 20px;
  font-size: 15px;
  line-height: 1.5;
  color: var(--faint);
}

.aa-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.aa-confirm {
  border-color: rgba(200, 155, 255, 0.45);
  color: var(--purple);
}

.toast {
  margin: 12px 24px 0;
  padding: 10px 14px;
  border-radius: 8px;
  font-size: 16px;
}

.toast.ok {
  border: 1px solid rgba(74, 222, 128, 0.5);
  background: rgba(74, 222, 128, 0.1);
  color: var(--green);
}

.toast.err {
  border: 1px solid rgba(255, 111, 103, 0.5);
  background: rgba(255, 111, 103, 0.1);
  color: var(--red);
}

.cards {
  /* Uniform grid: every card the same width and (fixed in SessionCard) height,
     independent of content. */
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(460px, 1fr));
  gap: 18px;
  padding: 16px 24px 28px;
}

</style>
