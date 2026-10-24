<script setup lang="ts">
// The AI guide: a side panel over every screen. It keeps the open thread across screens
// (lib/assistant.ts), attaches the screen as a removable chip, streams the answer as markdown
// with dashboard links, lists older threads and offers three questions in an empty thread.
// Actions the guide proposes show as cards (ActionCard) the user executes or dismisses;
// while one is still streaming, a placeholder card stands in for its raw block.
// An older thread can be deleted for good after a confirmation in a modal dialog.
import { computed, nextTick, ref, watch } from 'vue'
import { History, Plus, Sparkles, Trash2, X } from 'lucide-vue-next'
import {
  assistant,
  contextLabel,
  deleteThread,
  describeScreen,
  linkify,
  newThread,
  openThread,
  outcomeText,
  runState,
  sameContext,
  send,
  setOpen,
  showThreads,
  streamedAnswer,
  suggestions,
  type AssistantMessage,
  type ScreenContext,
  type ThreadSummary,
} from '@/lib/assistant'
import { useConfirm } from '@/lib/confirm'
import { fmtDayTime } from '@/lib/format'
import { renderMarkdown } from '@/lib/markdown'
import { usePage, useRepoId, useRoute, useRouteParams } from '@/lib/router'
import ActionCard from './ActionCard.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import Spinner from '@/components/ui/Spinner.vue'
import Tooltip from '@/components/ui/Tooltip.vue'

const props = withDefaults(defineProps<{ repos?: readonly string[] }>(), { repos: () => [] })

const page = usePage()
const repoId = useRepoId()
const screen = useRoute()
const params = useRouteParams()

const info = computed(() => describeScreen(page.value, repoId.value, screen.value, params.value))

// The chip of the screen: removed by the user until the screen changes.
const removed = ref<ScreenContext | null>(null)
const context = computed<ScreenContext | null>(() => {
  const shown = info.value.context
  if (!shown || (removed.value && sameContext(removed.value, shown))) return null
  return shown
})
watch(
  () => info.value.context,
  (next) => {
    if (removed.value && !sameContext(removed.value, next)) removed.value = null
  },
)
function removeContext(): void {
  removed.value = info.value.context
}

// The state of the shown run decides the suggestions ("Proč tenhle běh selhal?").
const shownRunState = ref<{ run: string; state: string | null } | null>(null)
watch(
  () => [assistant.open, info.value.context?.run ?? null] as const,
  async ([open, run]) => {
    if (!open || !run || shownRunState.value?.run === run) return
    const state = await runState(run)
    if (info.value.context?.run === run) shownRunState.value = { run, state }
  },
  { immediate: true },
)
const offered = computed(() => {
  const run = info.value.context?.run
  const state = run && shownRunState.value?.run === run ? shownRunState.value.state : null
  return suggestions(info.value.kind, state)
})

const thread = computed(() => assistant.thread)
const messages = computed<AssistantMessage[]>(() => thread.value?.messages ?? [])
const busy = computed(() => !!thread.value?.busy || assistant.sending)
const empty = computed(() => !assistant.loading && messages.value.length === 0 && !busy.value)
const answering = computed(() => harnessLabel(thread.value?.harness, thread.value?.model, thread.value?.thinking))

function harnessLabel(harness?: string, model?: string, thinking?: string | null): string {
  if (!harness) return ''
  return [harness, model, thinking].filter(Boolean).join(' · ')
}

/** The repository the links of a message point to: its question's screen, else the only one. */
function repoOf(index: number): string | null {
  for (let i = index; i >= 0; i--) {
    const repo = messages.value[i]?.screen?.repo
    if (repo) return repo
  }
  if (props.repos.length === 1) return props.repos[0] ?? null
  return repoId.value
}

function html(text: string, repo: string | null): string {
  return renderMarkdown(linkify(text, repo))
}

const streamRepo = computed(() => repoOf(messages.value.length - 1))
// A proposal being written shows as a placeholder card, never as its raw JSON.
const streamed = computed(() => streamedAnswer(assistant.streaming?.text ?? ''))

const { dialog, ask, confirm, cancel } = useConfirm()

async function remove(item: ThreadSummary): Promise<void> {
  const ok = await ask({
    title: 'Smazat vlákno?',
    message: `Vlákno „${item.title || 'Bez názvu'}“ se smaže natrvalo i se všemi zprávami. Tuto akci nelze vrátit.`,
    confirmLabel: 'Smazat vlákno',
    tone: 'danger',
  })
  if (ok) await deleteThread(item.id)
}

const draft = ref('')
const log = ref<HTMLElement | null>(null)

async function submit(text = draft.value): Promise<void> {
  const sent = await send(text, context.value)
  if (sent && text === draft.value) draft.value = ''
}

function onKey(event: KeyboardEvent): void {
  if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) {
    event.preventDefault()
    void submit()
  }
}

watch(
  () => [messages.value.length, assistant.streaming?.text.length ?? 0, assistant.open] as const,
  async () => {
    await nextTick()
    if (log.value) log.value.scrollTop = log.value.scrollHeight
  },
)
</script>

<template>
  <aside v-if="assistant.open" class="assistant" aria-label="AI průvodce" data-test="assistant-panel">
    <header class="head">
      <div class="head-title">
        <Sparkles :size="16" aria-hidden="true" />
        <strong>AI průvodce</strong>
        <span v-if="answering" class="who" data-test="assistant-harness">{{ answering }}</span>
        <span v-else class="who faint" data-test="assistant-harness">harness z nastavení počítače</span>
      </div>
      <div class="head-actions">
        <Tooltip text="Starší vlákna">
          <button
            type="button"
            class="icon"
            :class="{ active: assistant.listing }"
            aria-label="Starší vlákna"
            data-test="assistant-threads"
            @click="showThreads(!assistant.listing)"
          >
            <History :size="16" aria-hidden="true" />
          </button>
        </Tooltip>
        <Tooltip text="Nové vlákno">
          <button type="button" class="icon" aria-label="Nové vlákno" data-test="assistant-new" @click="newThread">
            <Plus :size="16" aria-hidden="true" />
          </button>
        </Tooltip>
        <Tooltip text="Zavřít">
          <button type="button" class="icon" aria-label="Zavřít" data-test="assistant-close" @click="setOpen(false)">
            <X :size="16" aria-hidden="true" />
          </button>
        </Tooltip>
      </div>
    </header>

    <section v-if="assistant.listing" class="threads" data-test="assistant-thread-list">
      <p v-if="assistant.threadsError" class="error" role="alert" data-test="assistant-threads-error">{{ assistant.threadsError }}</p>
      <p v-if="assistant.threads === null && !assistant.threadsError" class="faint"><Spinner /> Načítám vlákna…</p>
      <p v-else-if="assistant.threads && !assistant.threads.length" class="faint" data-test="assistant-no-threads">Zatím žádné vlákno.</p>
      <ul v-else-if="assistant.threads">
        <li v-for="item in assistant.threads" :key="item.id" class="thread-row">
          <button
            type="button"
            class="thread-item"
            :class="{ current: item.id === thread?.id }"
            data-test="assistant-thread-item"
            @click="openThread(item.id)"
          >
            <span class="thread-title">{{ item.title || 'Bez názvu' }}</span>
            <span class="thread-meta faint">
              {{ fmtDayTime(item.updated_at) }} · {{ item.messages }} zpráv · {{ harnessLabel(item.harness, item.model, item.thinking) }}
              <template v-if="item.busy"> · odpovídá</template>
            </span>
          </button>
          <Tooltip text="Smazat vlákno">
            <button
              type="button"
              class="icon thread-delete"
              aria-label="Smazat vlákno"
              data-test="assistant-thread-delete"
              :disabled="!!assistant.deleting"
              :aria-busy="assistant.deleting === item.id || undefined"
              @click="remove(item)"
            >
              <Spinner v-if="assistant.deleting === item.id" />
              <Trash2 v-else :size="16" aria-hidden="true" />
            </button>
          </Tooltip>
        </li>
      </ul>
    </section>

    <template v-else>
      <div ref="log" class="log" data-test="assistant-log">
        <p v-if="assistant.loading" class="faint"><Spinner /> Načítám vlákno…</p>
        <div v-if="empty" class="empty" data-test="assistant-empty">
          <p class="faint">Zeptej se na repa, tasky, běhy, PR, konfiguraci nebo knihovnu. Průvodce jen čte; změnu navrhne a provede se, až ji potvrdíš.</p>
          <button
            v-for="question in offered"
            :key="question"
            type="button"
            class="suggestion"
            data-test="assistant-suggestion"
            @click="submit(question)"
          >
            {{ question }}
          </button>
        </div>
        <template v-for="(message, index) in messages" :key="message.id">
          <div v-if="message.role === 'user'" class="msg user" data-test="assistant-user">
            <p class="user-text">{{ message.text }}</p>
            <span v-if="message.screen && contextLabel(message.screen)" class="sent-context faint">
              {{ contextLabel(message.screen) }}
            </span>
          </div>
          <p v-else-if="message.role === 'action'" class="msg outcome faint" :class="message.status" data-test="assistant-outcome">
            {{ outcomeText(message, messages) }}
          </p>
          <div v-else class="msg answer" data-test="assistant-answer">
            <div v-if="message.text" class="md" v-html="html(message.text, repoOf(index))" />
            <p v-if="message.error" class="error" data-test="assistant-answer-error">{{ message.error }}</p>
            <ActionCard v-for="action in message.actions ?? []" :key="action.id" :action="action" :thread-id="thread!.id" />
          </div>
        </template>
        <div v-if="busy" class="msg answer streaming" data-test="assistant-streaming">
          <p v-for="(tool, i) in assistant.streaming?.tools ?? []" :key="i" class="tool faint">{{ tool }}</p>
          <div v-if="streamed.text.trim()" class="md" v-html="html(streamed.text, streamRepo)" />
          <div v-for="n in streamed.pending" :key="`pending-${n}`" class="pending-action faint" data-test="assistant-action-pending">
            <Spinner /> Připravuji návrh akce…
          </div>
          <p class="faint"><Spinner /> Průvodce odpovídá…</p>
        </div>
      </div>

      <p v-if="assistant.error" class="error composer-error" data-test="assistant-error">{{ assistant.error }}</p>

      <form class="composer" @submit.prevent="submit()">
        <div v-if="context" class="chip" data-test="assistant-context">
          <span>{{ contextLabel(context) }}</span>
          <button type="button" class="chip-remove" aria-label="Odebrat kontext obrazovky" data-test="assistant-context-remove" @click="removeContext">
            <X :size="12" aria-hidden="true" />
          </button>
        </div>
        <textarea
          v-model="draft"
          rows="3"
          placeholder="Zeptej se průvodce…"
          aria-label="Zpráva průvodci"
          data-test="assistant-input"
          @keydown="onKey"
        />
        <button type="submit" class="send" :disabled="busy || !draft.trim()" data-test="assistant-send">Odeslat</button>
      </form>
    </template>
    <ConfirmDialog v-bind="dialog" @confirm="confirm" @cancel="cancel" />
  </aside>
</template>

<style scoped>
.assistant {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 20;
  display: flex;
  flex-direction: column;
  width: min(460px, 100vw);
  background: var(--panel);
  border-left: 1px solid var(--border);
  box-shadow: var(--shadow-pop);
}

.head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 14px 16px;
  border-bottom: 1px solid var(--border);
}

.head-title {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  color: var(--purple);
}

.head-title strong {
  color: var(--text);
  white-space: nowrap;
}

.who {
  overflow: hidden;
  font-family: var(--mono);
  font-size: 13px;
  color: var(--dim);
  text-overflow: ellipsis;
  white-space: nowrap;
}

.head-actions {
  display: flex;
  gap: 6px;
}

.icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
}

.icon.active {
  border-color: var(--purple);
}

.threads {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.threads ul {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.thread-row {
  display: flex;
  align-items: stretch;
  gap: 6px;
}

.thread-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
  text-align: left;
}

.thread-delete {
  align-self: center;
  flex: none;
}

.thread-item.current {
  border-color: var(--purple);
}

.thread-title {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.thread-meta {
  font-size: 13px;
}

.log {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.empty {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.suggestion {
  text-align: left;
}

.msg {
  max-width: 100%;
}

.user {
  align-self: flex-end;
  max-width: 85%;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

.user-text {
  margin: 0;
  white-space: pre-wrap;
}

.sent-context {
  display: block;
  margin-top: 4px;
  font-size: 12px;
}

.answer .md {
  font-size: 15px;
}

.answer :deep(.md code) {
  font-size: 14px;
}

.outcome {
  margin: 0;
  padding-left: 10px;
  border-left: 2px solid var(--border);
  font-size: 13px;
}

.outcome.done {
  border-left-color: var(--green);
}

.outcome.failed {
  border-left-color: var(--red);
}

.pending-action {
  margin-top: 8px;
  padding: 10px 12px;
  border: 1px dashed var(--purple);
  border-radius: 10px;
  background: var(--panel-2);
  font-size: 13px;
}

.tool {
  margin: 0;
  font-family: var(--mono);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.error {
  color: var(--red);
  white-space: pre-wrap;
}

.composer-error {
  margin: 0;
  padding: 0 16px;
}

.composer {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px 16px;
  border-top: 1px solid var(--border);
}

.chip {
  display: inline-flex;
  align-items: center;
  align-self: flex-start;
  gap: 6px;
  padding: 2px 4px 2px 10px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel-2);
  font-family: var(--mono);
  font-size: 12px;
  color: var(--dim);
}

.chip-remove {
  display: inline-flex;
  padding: 2px;
  border: none;
  border-radius: 999px;
  background: transparent;
  color: var(--dim);
}

textarea {
  resize: vertical;
  padding: 8px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-3);
  color: var(--text);
  font: inherit;
}

.send {
  align-self: flex-end;
}

.faint {
  color: var(--faint);
}
</style>
