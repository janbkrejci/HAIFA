<script setup lang="ts">
// Changes kept in the working tree while runs read base (D4): the shared config in .factory/
// (a banner at the top of the repo screen, its commit is reviewed on the Factory screen) and
// the backlog (a bar fixed at the bottom of the window, so it never moves the page while you
// click in it; one button commits it all at once).
import { computed } from 'vue'
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
    /** A bar fixed at the bottom with the files folded, instead of a banner in the page. */
    floating?: boolean
    committing?: boolean
    /** The last commit failed. */
    commitError?: string | null
    /** The status itself could not be read. */
    statusError?: string | null
  }>(),
  { floating: false, committing: false, commitError: null, statusError: null },
)
const emit = defineEmits<{ commit: [] }>()

const dirty = computed(() => (props.status && !props.status.clean ? props.status : null))
const sha = computed(() => shortSha(dirty.value?.commit))
const files = computed(() => {
  const n = dirty.value?.changes.length ?? 0
  return `${n} ${plural(n, 'soubor', 'soubory', 'souborů')}`
})
</script>

<template>
  <div
    v-if="dirty"
    class="uncommitted"
    :class="floating ? 'floating' : 'inline'"
    :role="floating ? 'status' : 'alert'"
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
    <details v-if="floating" class="files">
      <summary :data-test="`${kind}-files`">{{ files }}</summary>
      <ul>
        <li v-for="change in dirty.changes" :key="change.path" :data-test="`${kind}-change`">
          <span class="change-status">{{ change.status }}</span> {{ change.path }}
        </li>
      </ul>
    </details>
    <ul v-else class="files">
      <li v-for="change in dirty.changes" :key="change.path" :data-test="`${kind}-change`">
        <span class="change-status">{{ change.status }}</span> {{ change.path }}
      </li>
    </ul>
    <p v-if="commitError" class="commit-error" :data-test="`${kind}-commit-error`">
      Commit se nepodařil: {{ commitError }}
    </p>
  </div>
  <p v-else-if="statusError" class="status-error" :data-test="`${kind}-banner-error`">
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

.floating {
  position: fixed;
  left: 50%;
  bottom: 16px;
  z-index: 20;
  width: min(820px, calc(100vw - 32px));
  max-height: 50vh;
  overflow: auto;
  transform: translateX(-50%);
  padding: 10px 14px;
  border: 1px solid rgba(232, 182, 74, 0.55);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: 0 8px 28px rgba(0, 0, 0, 0.35);
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

.files summary {
  cursor: pointer;
}

.files ul,
ul.files {
  padding-left: 18px;
}

.files ul {
  margin: 4px 0 0;
}

.files li {
  color: var(--text);
  font-family: var(--mono);
}

.change-status {
  color: var(--dim);
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
