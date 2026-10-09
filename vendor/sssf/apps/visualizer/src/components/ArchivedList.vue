<script setup lang="ts">
import { onMounted, onUnmounted, ref, shallowRef } from 'vue'
import type { SessionSummary } from '../lib/types'
import {
  deleteArchivedSessions,
  deleteSession,
  fetchArchivedSessions,
  restoreSession,
} from '../lib/api'
import { fmtDate } from '../lib/format'
import { hrefFor } from '../lib/router'

const sessions = shallowRef<SessionSummary[]>([])
const apiError = ref<string | null>(null)
const loaded = ref(false)
const restoring = ref<string | null>(null)
// The run the confirm dialog is armed for. null = closed; nothing is deleted
// until this is set AND the confirm button is pressed.
const pendingDelete = ref<SessionSummary | null>(null)
const deleting = ref<string | null>(null)
// Armed separately from the per-row dialog: purging the list and deleting one
// run are different decisions and must not share a confirm state.
const purging = ref(false)
const askingPurge = ref(false)
const toast = ref<{ kind: 'ok' | 'err'; msg: string } | null>(null)

let timer: ReturnType<typeof setInterval> | undefined
let inflight = false

/**
 * Show a toast for a fixed window, restarting the clock on every call.
 *
 * The dismissal timer has to be CANCELLED, not merely replaced: two deletes in
 * quick succession used to leave the first timer running, so it fired on the
 * second toast and cut its message short by however long the first had already
 * been up. Every toast now gets the full window, and the last one wins.
 */
const TOAST_MS = 3000
let toastTimer: ReturnType<typeof setTimeout> | undefined

function showToast(kind: 'ok' | 'err', msg: string) {
  clearTimeout(toastTimer)
  toast.value = { kind, msg }
  toastTimer = setTimeout(() => (toast.value = null), TOAST_MS)
}

async function tick() {
  if (inflight) return
  inflight = true
  try {
    sessions.value = await fetchArchivedSessions()
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
  timer = setInterval(() => void tick(), 5000)
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  clearInterval(timer)
  clearTimeout(toastTimer)
  window.removeEventListener('keydown', onKeydown)
})

async function onRestore(adwId: string) {
  restoring.value = adwId
  try {
    await restoreSession(adwId)
    sessions.value = sessions.value.filter((s) => s.adw_id !== adwId)
    showToast('ok', `Restored ${adwId}`)
  } catch {
    showToast('err', `Failed to restore ${adwId}`)
    void tick()
  } finally {
    restoring.value = null
  }
}

function askDelete(s: SessionSummary) {
  pendingDelete.value = s
}

function cancelDelete() {
  pendingDelete.value = null
}

/**
 * Escape closes whichever dialog is open.
 *
 * Bound to the window, not to the backdrop: the backdrop is a plain div that
 * never takes focus, so a `keydown` handler on it only ever fires if the user
 * happens to have tabbed into it. The listener that actually works is the one
 * the key event reaches no matter what has focus.
 */
function onKeydown(e: KeyboardEvent) {
  if (e.key !== 'Escape') return
  if (!pendingDelete.value && !askingPurge.value) return
  e.preventDefault()
  cancelDelete()
  cancelPurge()
}

/**
 * Erase the run, then drop its row locally rather than waiting for the poll —
 * the list refreshes every 5s, and a row that lingers after a confirmed delete
 * reads as a failure. A real failure re-syncs from the server instead.
 */
async function confirmDelete() {
  const target = pendingDelete.value
  if (!target) return
  const adwId = target.adw_id
  pendingDelete.value = null
  deleting.value = adwId
  try {
    await deleteSession(adwId)
    sessions.value = sessions.value.filter((s) => s.adw_id !== adwId)
    showToast('ok', `Deleted ${adwId} and its session files`)
  } catch {
    showToast('err', `Failed to delete ${adwId}`)
    void tick()
  } finally {
    deleting.value = null
  }
}

function askPurge() {
  askingPurge.value = true
}

function cancelPurge() {
  askingPurge.value = false
}

async function confirmPurge() {
  askingPurge.value = false
  purging.value = true
  try {
    const count = await deleteArchivedSessions()
    sessions.value = []
    showToast('ok', `Deleted ${count} archived run${count === 1 ? '' : 's'} and their session files`)
  } catch {
    showToast('err', 'Failed to delete the archived runs')
    void tick()
  } finally {
    purging.value = false
  }
}

function archivedAt(s: SessionSummary): string {
  // archived rows keep their started_at; fall back to ended_at.
  return fmtDate(s.started_at) || fmtDate(s.ended_at) || '—'
}
</script>

<template>
  <div class="archived">
    <div v-if="apiError" class="error-bar">api unreachable — retrying {{ apiError }}</div>

    <div v-if="toast" :class="['toast', toast.kind]">{{ toast.msg }}</div>

    <div v-if="sessions.length" class="list-head">
      <span class="dim">{{ sessions.length }} archived runs</span>
      <button
        class="purge-btn"
        type="button"
        :disabled="purging"
        @click="askPurge"
      >
        {{ purging ? 'Deleting…' : 'Delete all' }}
      </button>
    </div>

    <div v-if="sessions.length" class="rows">
      <div v-for="s in sessions" :key="s.adw_id" class="row">
        <a class="row-link" :href="hrefFor(s.adw_id)">
          <span class="row-id">{{ s.adw_id }}</span>
          <span class="row-adw" :title="s.adw_name ?? ''">{{ s.adw_name ?? '—' }}</span>
          <span class="row-req" :title="s.request ?? ''">{{ s.request }}</span>
          <span class="row-date dim">{{ archivedAt(s) }}</span>
        </a>
        <button
          class="restore-btn"
          type="button"
          :disabled="restoring === s.adw_id || deleting === s.adw_id"
          @click="onRestore(s.adw_id)"
        >
          {{ restoring === s.adw_id ? 'Restoring…' : 'Restore' }}
        </button>
        <button
          class="delete-btn"
          type="button"
          :disabled="deleting === s.adw_id || restoring === s.adw_id"
          :title="`Permanently delete ${s.adw_id}`"
          @click="askDelete(s)"
        >
          {{ deleting === s.adw_id ? 'Deleting…' : 'Delete' }}
        </button>
      </div>
    </div>

    <div v-else-if="loaded" class="empty-state">No archived sessions.</div>
    <div v-else-if="!apiError" class="empty-state">loading archived sessions…</div>

    <Teleport to="body">
      <div v-if="askingPurge" class="del-backdrop" @click="cancelPurge">
        <div
          class="del-dialog"
          role="alertdialog"
          aria-modal="true"
          aria-label="Delete all archived runs?"
          @click.stop
        >
          <div class="del-title">Delete all {{ sessions.length }} archived runs?</div>
          <div class="del-body">
            <p class="del-hint">
              Removes every archived run's whole trace — phases, events, envelopes, gates —
              and deletes their session directories on disk, including prompts and raw agent
              output. Runs that are not archived are untouched.
              <strong>This cannot be undone.</strong>
            </p>
          </div>
          <div class="del-actions">
            <button class="del-act del-cancel" type="button" @click="cancelPurge">Cancel</button>
            <button class="del-act del-confirm" type="button" @click="confirmPurge">
              Delete all {{ sessions.length }}
            </button>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <div
        v-if="pendingDelete"
        class="del-backdrop"
        @click="cancelDelete"
      >
        <div
          class="del-dialog"
          role="alertdialog"
          aria-modal="true"
          :aria-label="`Delete session ${pendingDelete.adw_id}?`"
          @click.stop
        >
          <div class="del-title">Delete this run for good?</div>
          <div class="del-body">
            <code>{{ pendingDelete.adw_id }}</code>
            <span v-if="pendingDelete.adw_name" class="del-adw"> · {{ pendingDelete.adw_name }}</span>
            <p class="del-hint">
              Removes its whole trace — phases, events, envelopes, gates — and deletes its
              session directory on disk, including prompts and raw agent output.
              <strong>This cannot be undone.</strong>
            </p>
          </div>
          <div class="del-actions">
            <button class="del-act del-cancel" type="button" @click="cancelDelete">Cancel</button>
            <button class="del-act del-confirm" type="button" @click="confirmDelete">Delete</button>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.archived {
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

.purge-btn {
  flex: none;
  padding: 6px 14px;
  border: 1px solid rgba(255, 111, 103, 0.4);
  border-radius: 8px;
  background: rgba(255, 111, 103, 0.12);
  color: var(--red);
  font-family: inherit;
  font-size: 15px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.purge-btn:hover {
  background: rgba(255, 111, 103, 0.22);
  border-color: rgba(255, 111, 103, 0.6);
}

.purge-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.rows {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 16px 24px 28px;
}

.row {
  transition: background 0.15s ease, border-color 0.15s ease;
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 14px 18px;
  border: 1px solid var(--border-soft);
  border-radius: 12px;
  background: var(--surface);
}

.row-link {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 16px;
  color: inherit;
}

.row:has(.row-link:hover) {
  border-color: var(--border);
  background: var(--panel-2);
}

.row-id {
  font-family: var(--mono);
  font-size: 16px;
  font-weight: 700;
  color: var(--purple);
  flex: none;
}

.row-adw {
  font-family: var(--mono);
  font-size: 15px;
  color: var(--cyan);
  flex: none;
  min-width: 100px;
}

.row-req {
  flex: 1;
  font-size: 16px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-date {
  flex: none;
  font-size: 15px;
}

.restore-btn {
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

.restore-btn:hover {
  background: var(--panel-3);
  border-color: var(--border);
}

.restore-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

.delete-btn {
  flex: none;
  padding: 6px 14px;
  border: 1px solid rgba(255, 111, 103, 0.4);
  border-radius: 8px;
  background: rgba(255, 111, 103, 0.12);
  color: var(--red);
  font-family: inherit;
  font-size: 15px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.delete-btn:hover {
  background: rgba(255, 111, 103, 0.22);
  border-color: rgba(255, 111, 103, 0.6);
}

.delete-btn:disabled {
  opacity: 0.6;
  cursor: default;
}

/* Teleported to body, so it renders above everything; styles stay scoped here. */
.del-backdrop {
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

.del-dialog {
  width: min(460px, calc(100vw - 48px));
  padding: 24px;
  border: 1px solid var(--border);
  border-radius: 16px;
  background: var(--surface);
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);
}

.del-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 12px;
}

.del-body {
  font-size: 16px;
  color: var(--dim);
  margin-bottom: 20px;
}

.del-body code {
  font-family: var(--mono);
  font-size: 15px;
  color: var(--purple);
  background: var(--panel-2);
  border: 1px solid var(--border-soft);
  border-radius: 4px;
  padding: 1px 6px;
}

.del-adw {
  color: var(--cyan);
}

.del-hint {
  margin: 12px 0 0;
  font-size: 15px;
  line-height: 1.5;
  color: var(--faint);
}

.del-hint strong {
  color: var(--red);
  font-weight: 700;
}

.del-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.del-act {
  padding: 8px 18px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font-family: inherit;
  font-size: 15px;
  cursor: pointer;
  transition: background 0.15s ease, border-color 0.15s ease;
}

.del-act:hover {
  background: var(--panel-3);
  border-color: var(--border);
}

.del-cancel {
  color: var(--dim);
}

.del-confirm {
  background: rgba(255, 111, 103, 0.15);
  border-color: rgba(255, 111, 103, 0.4);
  color: var(--red);
}

.del-confirm:hover {
  background: rgba(255, 111, 103, 0.25);
  border-color: rgba(255, 111, 103, 0.6);
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
</style>
