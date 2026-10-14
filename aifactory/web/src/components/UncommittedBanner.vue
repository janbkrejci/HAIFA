<script setup lang="ts">
// Changes kept in the working tree while runs read base (D4): the shared config in .factory/
// (a banner at the top of the repo screen, its commit is reviewed on the Factory screen) and
// the backlog (a red chip in the topbar, so it never moves the page while you click in it; the
// chip opens a panel with the files and one button that commits it all at once).
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { TriangleAlert } from 'lucide-vue-next'
import Spinner from '@/components/ui/Spinner.vue'
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
    committing?: boolean
    /** The last commit failed. */
    commitError?: string | null
    /** The status itself could not be read. */
    statusError?: string | null
    /** The changes wait in this pull request (`base_changes: pr`). */
    pr?: { url: string; branch: string } | null
  }>(),
  { chip: false, committing: false, commitError: null, statusError: null, pr: null },
)
const emit = defineEmits<{ commit: [] }>()

const dirty = computed(() => (props.status && !props.status.clean ? props.status : null))
const sha = computed(() => shortSha(dirty.value?.commit))
const files = computed(() => {
  const n = dirty.value?.changes.length ?? 0
  return `${n} ${plural(n, 'soubor', 'soubory', 'souborů')}`
})

/** The chip's panel is open. */
const open = ref(false)
const root = ref<HTMLElement | null>(null)
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
})
// a failed commit shows its reason at once
watch(() => props.commitError, (error) => {
  if (error && props.chip) open.value = true
})
watch(dirty, (value) => {
  if (!value) open.value = false
})
onBeforeUnmount(() => {
  open.value = false
  document.removeEventListener('mousedown', onOutside, true)
  document.removeEventListener('keydown', onKey)
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
    <button
      type="button"
      class="chip"
      :aria-expanded="open"
      :data-test="`${kind}-chip`"
      @click="open = !open"
    >
      <Spinner v-if="committing" />
      <TriangleAlert v-else :size="14" aria-hidden="true" />
      Necommitnutý {{ title.toLocaleLowerCase('cs') }} · {{ files }}
    </button>
    <div v-show="open" class="panel" :data-test="`${kind}-panel`">
      <p>
        <slot name="title">{{ title }}</slot> má necommitnuté změny. Běhy používají
        <code>{{ dirty.base }}</code><template v-if="sha"> (<code>{{ sha }}</code>)</template>, dokud změny
        necommitneš.
      </p>
      <ul class="files">
        <li v-for="change in dirty.changes" :key="change.path" :data-test="`${kind}-change`">
          <span class="change-status">{{ change.status }}</span> {{ change.path }}
        </li>
      </ul>
      <p v-if="pr" class="pr" :data-test="`${kind}-pr`">
        Změny čekají v pull requestu <a :href="pr.url" target="_blank" rel="noopener">{{ pr.branch }}</a>. Po jeho mergi použij v záložce Factory Stáhnout konfiguraci z base.
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
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid currentColor;
  border-radius: 999px;
  background: color-mix(in srgb, var(--red) 12%, var(--panel-2));
  color: var(--red);
  font: inherit;
  font-size: 12px;
  white-space: nowrap;
  cursor: pointer;
}

.chip:hover {
  background: color-mix(in srgb, var(--red) 20%, var(--panel-2));
}

.panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 30;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  width: min(560px, calc(100vw - 32px));
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

.panel .files {
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
