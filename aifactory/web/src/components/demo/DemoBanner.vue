<script setup lang="ts">
import { t } from '@/lib/i18n'
// The strip above every screen of the sample repository: what it is, what the last
// "Vyzkoušet na ukázce" started, and the way out (own repo, remove the sample).
import { computed } from 'vue'
import { Plus } from 'lucide-vue-next'
import { DEMO_TASK, lastStart } from '@/lib/demo'
import { REPOS_ADD_HREF, runHref } from '@/lib/router'
import RemoveDemoButton from './RemoveDemoButton.vue'

const props = defineProps<{ repoId: string; path?: string | null }>()
const start = computed(() => (lastStart.value?.repoId === props.repoId ? lastStart.value : null))
</script>

<template>
  <section class="demo-banner" data-test="demo-banner">
    <p class="what">
      <strong>{{ t('dashboard.demoRepo') }}</strong>
      {{ t('dashboard.demoIntro') }}
    </p>
    <p v-if="start?.runId" class="started" data-test="demo-started">
      {{ t('dashboard.demoRunning', { task: DEMO_TASK }) }}<template v-if="start.harness"> {{ t('dashboard.demoHarness', { harness: start.harness.harness, model: start.harness.model }) }}</template>:
      <a :href="runHref(start.runId)" data-test="demo-run-link">{{ t('dashboard.watchRun', { id: start.runId }) }}</a>
    </p>
    <p v-else-if="start && !start.error" class="started" data-test="demo-started">
      {{ t('dashboard.demoStarting', { task: DEMO_TASK }) }}
    </p>
    <p v-if="start?.error" class="error" role="alert" data-test="demo-start-error">
      {{ t('dashboard.demoStartFailed', { task: DEMO_TASK, error: start.error }) }}
    </p>
    <div class="actions">
      <a :href="REPOS_ADD_HREF" class="add-link" data-test="demo-add-repo"><Plus :size="14" aria-hidden="true" /> {{ t('dashboard.addOwnRepo') }}</a>
      <RemoveDemoButton :path="path" />
    </div>
  </section>
</template>

<style scoped>
.demo-banner { display: flex; flex-wrap: wrap; align-items: center; gap: 8px 16px; margin: 12px 28px 0; padding: 10px 16px; border: 1px solid var(--cyan); border-radius: 10px; background: var(--panel-2); }
.demo-banner p { margin: 0; }
.what { flex: 1 1 320px; color: var(--dim); }
.what strong { color: var(--cyan); }
.started { flex-basis: 100%; }
.error { flex-basis: 100%; color: var(--red); }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-left: auto; }
.add-link { display: inline-flex; align-items: center; gap: 6px; color: var(--green); font-weight: 600; }
</style>
