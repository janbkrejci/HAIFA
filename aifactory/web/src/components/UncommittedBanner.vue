<script setup lang="ts">
import './ui/statusIconChip.css'
// Changes kept in the working tree while runs read base (D4), as red chips in the topbar (so they
// never move the page while you click in it): the backlog chip opens a short panel with the
// number of changes and one button that commits it all at once, kept inside the viewport; the config chip (`panel` off) lists the files in its
// tooltip and opens the reviewed commit of .factory/ on the Factory screen. Without `chip` it
// is a banner in the page.
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { TriangleAlert } from 'lucide-vue-next'
import Spinner from '@/components/ui/Spinner.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import type { CommitStatus } from '@/lib/commitStatus'
import { plural, shortSha } from '@/lib/format'

const props = withDefaults(
  defineProps<{
    /** Prefix of the data-test ids: `<kind>-banner`, `<kind>-commit`, `<kind>-change`, … */
    kind: string
    /** What has the changes ("Backlog"); the `title` slot may replace it with markup. */
    title: string
    status: CommitStatus | null
    commitLabel: string
    /** A chip (in the topbar) opening a panel with the files, instead of a banner in the page. */
    chip?: boolean
    /** The chip's text without the file count (default: "Necommitnutý <title>"). */
    chipText?: string
    /** The chip opens its panel; off, a click on the chip emits `commit` at once. */
    panel?: boolean
    committing?: boolean
    /** The last commit failed. */
    commitError?: string | null
    commitWarnings?: string[]
    /** The status itself could not be read. */
    statusError?: string | null
    /** The changes wait in this pull request (`base_changes: pr`). */
    pr?: { url: string; branch: string } | null
  }>(),
  { chip: false, chipText: undefined, panel: true, committing: false, commitError: null, commitWarnings: () => [], statusError: null, pr: null },
)
const emit = defineEmits<{ commit: [] }>()

const dirty = computed(() => (props.status && !props.status.clean ? props.status : null))
const sha = computed(() => shortSha(dirty.value?.commit))
const files = computed(() => {
  const n = dirty.value?.changes.length ?? 0
  return `${n} ${plural(n, 'soubor', 'soubory', 'souborů')}`
})

const changes = computed(() => {
  const n = dirty.value?.changes.length ?? 0
  return `${n} ${plural(n, 'změna', 'změny', 'změn')}`
})

const label = computed(() => props.chipText ?? `Necommitnutý ${props.title.toLocaleLowerCase('cs')}`)
const paths = computed(() => dirty.value?.changes.map((c) => c.path).join(', ') ?? '')
const description = computed(() => `${label.value} · ${files.value}: ${paths.value}`)
function onChip() {
  if (props.panel) open.value = !open.value
  else emit('commit')
}

/** The chip's panel is open. */
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const panelEl = ref<HTMLElement | null>(null)
/** Viewport position of the open panel: under the chip, right-aligned, clamped to the window. */
const GAP = 8
const pos = reactive({ top: 0, left: 0, measured: false })
function place() {
  const chip = root.value
  const panelBox = panelEl.value
  if (!chip || !panelBox) return
  const r = chip.getBoundingClientRect()
  const width = panelBox.getBoundingClientRect().width
  const maxLeft = Math.max(GAP, window.innerWidth - width - GAP)
  pos.top = r.bottom + GAP
  pos.left = Math.min(Math.max(r.right - width, GAP), maxLeft)
  pos.measured = true
}
const panelStyle = computed(() =>
  pos.measured ? { top: `${pos.top}px`, left: `${pos.left}px` } : { visibility: 'hidden' as const },
)
function onOutside(event: Event) {
  const target = event.target as Node | null
  if (target && root.value?.contains(target)) return
  open.value = false
}
function onKey(event: Event) {
  if ((event as KeyboardEvent).key === 'Escape') open.value = false
}
watch(open, (on) => {
  const method = on ? 'addEventListener' : 'removeEventListener'
  document[method]('mousedown', onOutside, true)
  document[method]('keydown', onKey)
  window[method]('resize', place)
  window[method]('scroll', place, true)
  pos.measured = false
  if (on) void nextTick(place)
})
// a failed commit shows its reason at once
watch(() => props.commitError, (error) => {
  if (error && props.chip && props.panel) open.value = true
})
watch(() => props.commitWarnings, (warnings) => {
  if (warnings.length && props.chip && props.panel) open.value = true
})
watch(dirty, (value) => {
  if (!value) open.value = false
})
onBeforeUnmount(() => {
  open.value = false
  document.removeEventListener('mousedown', onOutside, true)
  document.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', place)
  window.removeEventListener('scroll', place, true)
})
</script>

<template>
  <div
    v-if="dirty && chip"
    ref="root"
    class="uncommitted chip-wrap"
    role="status"
    :data-test="`${kind}-banner`"
  >
    <Tooltip :text="description">
      <button
        type="button"
        class="status-icon-chip chip"
        :aria-label="description"
        :aria-expanded="panel ? open : undefined"
        :data-test="`${kind}-chip`"
        @click="onChip"
      >
        <Spinner v-if="committing" />
        <TriangleAlert v-else :size="14" aria-hidden="true" />
        <span class="status-count" aria-hidden="true">{{ dirty.changes.length }}</span>
      </button>
    </Tooltip>
    <div
      v-if="panel"
      v-show="open"
      ref="panelEl"
      class="panel"
      :style="panelStyle"
      :data-test="`${kind}-panel`"
    >
      <p :data-test="`${kind}-summary`">Commitne se {{ changes }}.</p>
      <p v-if="pr" class="pr" :data-test="`${kind}-pr`">
        Změny čekají v pull requestu <a :href="pr.url" target="_blank" rel="noopener">{{ pr.branch }}</a>. Po jeho mergi použij v záložce Factory Stáhnout konfiguraci z base.
      </p>
      <p v-for="warning in commitWarnings" :key="warning" class="pr" :data-test="`${kind}-commit-warning`">
        {{ warning }}
      </p>
      <p v-if="commitError" class="commit-error" :data-test="`${kind}-commit-error`">
        Commit se nepodařil: {{ commitError }}
      </p>
      <button
        type="button"
        class="commit"
        :data-test="`${kind}-commit`"
        :disabled="committing"
        :aria-busy="committing || undefined"
        @click="emit('commit')"
      >
        <Spinner v-if="committing" />
        {{ commitLabel }}
      </button>
    </div>
  </div>
  <div
    v-else-if="dirty"
    class="uncommitted inline"
    role="alert"
    :data-test="`${kind}-banner`"
  >
    <div class="line">
      <p>
        <slot name="title">{{ title }}</slot> má necommitnuté změny. Běhy používají
        <code>{{ dirty.base }}</code><template v-if="sha"> (<code>{{ sha }}</code>)</template>, dokud změny
        necommitneš.
      </p>
      <button
        type="button"
        class="commit"
        :data-test="`${kind}-commit`"
        :disabled="committing"
        :aria-busy="committing || undefined"
        @click="emit('commit')"
      >
        <Spinner v-if="committing" />
        {{ commitLabel }}
      </button>
    </div>
    <ul class="files">
      <li v-for="change in dirty.changes" :key="change.path" :data-test="`${kind}-change`">
        <span class="change-status">{{ change.status }}</span> {{ change.path }}
      </li>
    </ul>
    <p v-if="pr" class="pr" :data-test="`${kind}-pr`">
      Změny čekají v pull requestu <a :href="pr.url" target="_blank" rel="noopener">{{ pr.branch }}</a>. Po jeho mergi použij v záložce Factory Stáhnout konfiguraci z base.
    </p>
    <p v-for="warning in commitWarnings" :key="warning" class="pr" :data-test="`${kind}-commit-warning`">
      {{ warning }}
    </p>
    <p v-if="commitError" class="commit-error" :data-test="`${kind}-commit-error`">
      Commit se nepodařil: {{ commitError }}
    </p>
  </div>
  <p v-else-if="statusError && !chip" class="status-error" :data-test="`${kind}-banner-error`">
    <slot name="title">{{ title }}</slot>: stav nelze zjistit ({{ statusError }})
  </p>
</template>

<style scoped>
.uncommitted {
  color: var(--amber);
}

.inline {
  margin: 12px 28px 0;
  padding: 8px 14px;
  border: 1px solid rgba(232, 182, 74, 0.45);
  border-radius: 8px;
  background: rgba(232, 182, 74, 0.08);
}

.chip-wrap {
  position: relative;
  color: var(--red);
}

.chip {
  background: color-mix(in srgb, var(--red) 12%, var(--panel-2));
  color: var(--red);
}

.chip:hover {
  background: color-mix(in srgb, var(--red) 20%, var(--panel-2));
}

.panel {
  position: fixed;
  z-index: 30;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  width: max-content;
  max-width: min(420px, calc(100vw - 16px));
  max-height: 60vh;
  overflow: auto;
  padding: 12px 14px;
  border: 1px solid color-mix(in srgb, var(--red) 55%, transparent);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
  color: var(--text);
  font-size: 14px;
}

.panel p {
  margin: 0;
}

.line {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
}

.line p {
  flex: 1;
  min-width: 240px;
  margin: 0;
}

.commit {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border: 1px solid rgba(232, 182, 74, 0.55);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

.commit:disabled {
  opacity: 0.6;
  cursor: default;
}

.files {
  margin: 6px 0 0;
  color: var(--dim);
  font-size: 14px;
}

ul.files {
  padding-left: 18px;
}

.files li {
  color: var(--text);
  font-family: var(--mono);
}

.change-status {
  color: var(--dim);
}

.pr {
  margin: 6px 0 0;
  color: var(--text);
}

.pr a {
  color: var(--blue);
}

.commit-error {
  margin: 6px 0 0;
  color: var(--red);
}

.status-error {
  margin: 8px 28px 0;
  color: var(--faint);
  font-size: 14px;
}
</style>
