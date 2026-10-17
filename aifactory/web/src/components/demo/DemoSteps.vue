<script setup lang="ts">
// In the run detail of the sample: the steps of its run (worktree, build, test, review, PR,
// merge) with a short explanation each; after the merge the way to an own repository.
import { computed } from 'vue'
import { Check, Circle, LoaderCircle, Plus } from 'lucide-vue-next'
import { demoFinished, demoSteps } from '@/lib/demo'
import type { PhaseDot, RunSummary } from '@/lib/runs'
import { REPOS_ADD_HREF, reviewHref } from '@/lib/router'
import RemoveDemoButton from './RemoveDemoButton.vue'

const props = defineProps<{ run: RunSummary; phases: readonly PhaseDot[] }>()
const steps = computed(() => demoSteps(props.run, props.phases))
const current = computed(() => steps.value.find((s) => s.state === 'current') ?? null)
const finished = computed(() => demoFinished(props.run))
const waitsForReview = computed(() => current.value?.id === 'merge')
</script>

<template>
  <section class="demo-steps" aria-label="Co se v ukázce děje" data-test="demo-steps">
    <h3>Co se právě děje</h3>
    <ol>
      <li v-for="step in steps" :key="step.id" :class="step.state" :data-step="step.id" :data-state="step.state">
        <Check v-if="step.state === 'done'" :size="15" aria-hidden="true" />
        <LoaderCircle v-else-if="step.state === 'current'" :size="15" class="spin" aria-hidden="true" />
        <Circle v-else :size="15" aria-hidden="true" />
        <span class="title">{{ step.title }}</span>
        <span v-if="step.state === 'current'" class="text">{{ step.text }}</span>
      </li>
    </ol>
    <p v-if="waitsForReview" class="next" data-test="demo-review-hint">
      Běh je hotový a PR čeká na tebe: <a :href="reviewHref(run.task_id)" data-test="demo-review-link">otevřít Review a schválit</a>.
    </p>
    <div v-if="finished" class="finished" data-test="demo-finished">
      <p>Hotovo: ukázka prošla celým cyklem task, běh, PR a merge. Teď to zkus na vlastním repozitáři.</p>
      <div class="actions">
        <a :href="REPOS_ADD_HREF" class="add-link" data-test="demo-finished-add-repo"><Plus :size="14" aria-hidden="true" /> Přidat vlastní repozitář</a>
        <RemoveDemoButton />
      </div>
    </div>
  </section>
</template>

<style scoped>
.demo-steps { margin: 12px 0; padding: 12px 16px; border: 1px solid var(--cyan); border-radius: 10px; background: var(--panel-2); }
h3 { margin: 0 0 8px; font-size: 15px; color: var(--cyan); }
ol { display: flex; flex-direction: column; gap: 4px; margin: 0; padding: 0; list-style: none; }
li { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 8px; color: var(--faint); }
li svg { flex: none; align-self: center; }
li.done { color: var(--green); }
li.current { color: var(--text); }
li.current .title { font-weight: 700; }
.text { flex: 1 1 260px; color: var(--dim); }
.spin { animation: spin 1s linear infinite; color: var(--blue); }
.next { margin: 10px 0 0; }
.finished { margin-top: 10px; }
.finished p { margin: 0 0 8px; color: var(--green); font-weight: 600; }
.actions { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; }
.add-link { display: inline-flex; align-items: center; gap: 6px; color: var(--green); font-weight: 600; }
</style>
