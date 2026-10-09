<script setup lang="ts">
import { errorText } from '../../lib/format'
// Folder browser of the Add repository page: a modal that starts in the home folder
// (GET /api/fs/dirs), enters subfolders, goes up and returns the chosen folder. Esc closes.
import { nextTick, ref, watch } from 'vue'
import { ArrowUp, Folder } from 'lucide-vue-next'
import { fetchDirs, type FsDirs } from '@/lib/api'
import Spinner from '@/components/ui/Spinner.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ choose: [path: string]; close: [] }>()

const dirs = ref<FsDirs | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)
const panel = ref<HTMLElement | null>(null)
let generation = 0

async function load(path?: string): Promise<void> {
  const mine = ++generation
  loading.value = true
  error.value = null
  try {
    const data = await fetchDirs(path)
    if (mine !== generation) return
    dirs.value = data
  } catch (err) {
    if (mine !== generation) return
    error.value = errorText(err)
  } finally {
    if (mine === generation) loading.value = false
  }
}

watch(
  () => props.open,
  async (open) => {
    if (!open) return
    dirs.value = null
    void load()
    await nextTick()
    panel.value?.focus()
  },
  { immediate: true },
)

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @mousedown.self="emit('close')">
      <div
        ref="panel"
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="folder-browser-title"
        tabindex="-1"
        data-test="folder-browser"
        @keydown="onKeydown"
      >
        <h2 id="folder-browser-title" class="modal-title">Vybrat složku</h2>
        <div class="current">
          <button
            type="button"
            class="btn"
            :disabled="!dirs || dirs.parent === null || loading"
            data-test="browser-up"
            @click="dirs?.parent && load(dirs.parent)"
          >
            <ArrowUp :size="14" aria-hidden="true" /> Nahoru
          </button>
          <span class="path mono" data-test="browser-path">{{ dirs?.path ?? '' }}</span>
          <Spinner v-if="loading" />
        </div>
        <p v-if="error" class="error" data-test="browser-error">{{ error }}</p>
        <ul v-if="dirs" class="entries">
          <li v-if="!dirs.entries.length" class="none">Žádné podsložky.</li>
          <li v-for="entry in dirs.entries" :key="entry.path">
            <button type="button" class="entry" data-test="browser-entry" @click="load(entry.path)">
              <Folder :size="14" aria-hidden="true" />
              <span class="name">{{ entry.name }}</span>
              <span v-if="entry.is_git" class="tag git" data-test="tag-git">git</span>
              <span v-if="entry.has_factory" class="tag factory" data-test="tag-factory">factory</span>
            </button>
          </li>
        </ul>
        <p v-if="dirs?.truncated" class="note" data-test="browser-truncated">Zobrazeno prvních 500 složek</p>
        <div class="modal-actions">
          <button type="button" class="btn" data-test="browser-cancel" @click="emit('close')">Zrušit</button>
          <button
            type="button"
            class="btn ok"
            :disabled="!dirs || loading"
            data-test="browser-choose"
            @click="dirs && emit('choose', dirs.path)"
          >
            Vybrat tuto složku
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: var(--z-modal);
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(3, 6, 12, 0.6);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
}

:global([data-theme='light']) .modal-backdrop {
  background: rgba(20, 30, 50, 0.35);
}

.modal {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  max-width: min(680px, calc(100vw - 32px));
  max-height: calc(100vh - 64px);
  padding: 20px 22px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background-color: var(--panel);
  color: var(--text);
  box-shadow: var(--shadow-pop);
}

.modal:focus {
  outline: none;
}

.modal-title {
  margin: 0;
  font-size: 19px;
  font-weight: 700;
}

.current {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.path {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--dim);
}

.entries {
  flex: 1;
  min-height: 120px;
  overflow-y: auto;
  margin: 0;
  padding: 4px;
  list-style: none;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
}

.entry {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 6px 10px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.entry:hover {
  background: rgba(108, 182, 255, 0.14);
}

.name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tag {
  padding: 0 6px;
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 12px;
}

.tag.git {
  color: var(--blue);
}

.tag.factory {
  color: var(--purple);
}

.none,
.note {
  margin: 0;
  padding: 6px 10px;
  color: var(--faint);
  font-size: 14px;
}

.error {
  margin: 0;
  color: var(--red);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.btn:disabled {
  cursor: default;
  opacity: 0.6;
}

.btn.ok {
  border-color: rgba(74, 222, 128, 0.55);
  color: var(--green);
  font-weight: 700;
}
</style>
