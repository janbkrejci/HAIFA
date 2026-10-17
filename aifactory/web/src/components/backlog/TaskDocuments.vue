<script setup lang="ts">
// Task card with tabs: the rendered task body (Zadání, shown first) and the read-only
// markdown documents (backlog item, spec and doc). The tabs are the card's only label; every
// tab shows rendered markdown only, without a source view. The server finds the documents by the
// task id; a missing one is listed but cannot be opened.
import { computed, ref, watch } from 'vue'
import { documentMarkdown, fetchTaskDocuments, type TaskDocument } from '@/lib/backlog'
import { errorText } from '@/lib/format'
import MarkdownView from '@/components/ui/MarkdownView.vue'
import Spinner from '@/components/ui/Spinner.vue'
import Tooltip from '@/components/ui/Tooltip.vue'

const props = defineProps<{ taskId: string; body: string }>()

const documents = ref<TaskDocument[]>([])
const loading = ref(false)
const error = ref<string | null>(null)
/** The open tab: `body` is the task body, otherwise a document kind. */
const selected = ref<TaskDocument['kind'] | 'body'>('body')

let token = 0

async function load(taskId: string) {
  const mine = ++token
  loading.value = true
  error.value = null
  selected.value = 'body'
  try {
    const data = await fetchTaskDocuments(taskId)
    if (mine !== token) return
    documents.value = Array.isArray(data?.documents) ? data.documents : []
  } catch (e) {
    if (mine !== token) return
    documents.value = []
    error.value = errorText(e)
  } finally {
    if (mine === token) loading.value = false
  }
}

watch(() => props.taskId, (id) => void load(id), { immediate: true })

const current = computed(() => documents.value.find((d) => d.kind === selected.value) ?? null)
const source = computed(() => (current.value?.content == null ? '' : documentMarkdown(current.value.content)))

function open(doc: TaskDocument) {
  if (doc.exists) selected.value = doc.kind
}

function tip(doc: TaskDocument): string {
  if (doc.exists) return doc.path
  return doc.problem ? `${doc.path} – ${doc.problem}` : `${doc.path} – soubor neexistuje`
}
</script>

<template>
  <section class="card task-docs" data-test="task-documents">
    <div class="doc-tabs" role="tablist" aria-label="Dokumenty tasku">
      <button
        type="button"
        role="tab"
        data-test="doc-task"
        :class="{ active: selected === 'body' }"
        :aria-selected="selected === 'body'"
        @click="selected = 'body'"
      >
        Zadání
      </button>
      <Tooltip v-for="doc in documents" :key="doc.kind" :text="tip(doc)">
        <button
          type="button"
          role="tab"
          :class="{ active: selected === doc.kind, missing: !doc.exists }"
          :data-test="`doc-${doc.kind}`"
          :data-exists="doc.exists"
          :aria-selected="selected === doc.kind"
          :disabled="!doc.exists"
          @click="open(doc)"
        >
          {{ doc.label }}
          <span v-if="!doc.exists" class="tag" data-test="doc-missing">chybí</span>
        </button>
      </Tooltip>
      <Spinner v-if="loading" />
    </div>
    <p v-if="error" class="error" data-test="docs-error">{{ error }}</p>
    <div v-if="selected === 'body'" class="doc-body">
      <MarkdownView :source="body" empty="Zadání je prázdné." preview-only data-test="body" />
    </div>
    <div v-else-if="current" class="doc-body" :data-doc="current.kind">
      <div class="doc-path mono" data-test="doc-path">{{ current.path }}</div>
      <p v-if="current.content == null" class="faint" data-test="doc-problem">
        Obsah nejde zobrazit{{ current.problem ? `: ${current.problem}` : '' }}.
      </p>
      <MarkdownView v-else :source="source" empty="Dokument je prázdný." preview-only data-test="doc-content" />
    </div>
  </section>
</template>

<style scoped>
.card {
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--surface);
}

.doc-tabs {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}

.doc-tabs button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.doc-tabs button.active {
  border-color: var(--blue);
  background: color-mix(in srgb, var(--blue) 18%, var(--panel));
  color: var(--blue);
}

.doc-tabs button.missing {
  color: var(--faint);
  border-style: dashed;
  cursor: default;
  /* A disabled button gets no mouse events; let the tooltip anchor get the hover. */
  pointer-events: none;
}

.tag {
  font-size: 12px;
  color: var(--amber);
}

.doc-body {
  margin-top: 12px;
}

.doc-path {
  margin-bottom: 6px;
  font-family: var(--mono);
  font-size: 13px;
  color: var(--faint);
  overflow-wrap: anywhere;
}

.error {
  color: var(--red);
}
</style>
