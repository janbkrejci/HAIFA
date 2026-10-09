<script setup lang="ts">
// The first-visit guide on the overview and on #/setup: seven steps from this machine to the
// first backlog project, each with its state and a link; the next one is highlighted. When all
// are done it disappears. Inputs given as props are used as they are, the rest is read.
import { computed, onMounted, ref, watch } from 'vue'
import { Check, ChevronDown, ChevronRight } from 'lucide-vue-next'
import { fetchFactoryRoster, fetchMachineCheck, fetchRepos, getGlobal, type MachineCheck, type RepoItem } from '@/lib/api'
import { fetchLibrary, type LibraryStatus } from '@/lib/library'
import { focusRepo, gettingStartedSteps, nextStep } from '@/lib/gettingStarted'

const props = withDefaults(
  defineProps<{
    repos?: RepoItem[] | null
    check?: MachineCheck | null
    library?: LibraryStatus | null
  }>(),
  { repos: undefined, check: undefined, library: undefined },
)

const ownRepos = ref<RepoItem[] | null>(null)
const ownCheck = ref<MachineCheck | null>(null)
const ownLibrary = ref<LibraryStatus | null>(null)
const rosterAgents = ref<number | null>(null)
const projects = ref<number | null>(null)
const loaded = ref(false)
const open = ref(true)

const repos = computed(() => (props.repos !== undefined ? props.repos : ownRepos.value))
const check = computed(() => (props.check !== undefined ? props.check : ownCheck.value))
const library = computed(() => (props.library !== undefined ? props.library : ownLibrary.value))
const focus = computed(() => focusRepo(repos.value))
const steps = computed(() =>
  gettingStartedSteps({ check: check.value, library: library.value, repos: repos.value, rosterAgents: rosterAgents.value, projects: projects.value }),
)
const next = computed(() => nextStep(steps.value))
const doneCount = computed(() => steps.value.filter((s) => s.done).length)

async function loadOwn(): Promise<void> {
  const [c, l, r] = await Promise.allSettled([
    props.check === undefined ? fetchMachineCheck() : Promise.resolve(null),
    props.library === undefined ? fetchLibrary() : Promise.resolve(null),
    props.repos === undefined ? fetchRepos() : Promise.resolve(null),
  ])
  if (c.status === 'fulfilled' && c.value) ownCheck.value = c.value
  if (l.status === 'fulfilled' && l.value) ownLibrary.value = l.value
  if (r.status === 'fulfilled' && r.value) ownRepos.value = r.value.repos ?? []
  loaded.value = true
}

let repoGeneration = 0
/** The roster and the backlog projects of the installed focus repo. */
async function loadRepo(): Promise<void> {
  const mine = ++repoGeneration
  const repo = focus.value
  rosterAgents.value = null
  projects.value = null
  if (!repo || repo.status !== 'ok') return
  const [roster, backlog] = await Promise.allSettled([
    fetchFactoryRoster(repo.id),
    getGlobal<{ items?: unknown[] }>(`/repos/${encodeURIComponent(repo.id)}/backlog`),
  ])
  if (mine !== repoGeneration) return
  rosterAgents.value = roster.status === 'fulfilled' ? (roster.value.agents?.length ?? 0) : null
  projects.value = backlog.status === 'fulfilled' ? (backlog.value.items?.length ?? 0) : null
}

watch(() => `${focus.value?.id ?? ''}:${focus.value?.status ?? ''}`, () => void loadRepo())
onMounted(() => {
  void loadOwn()
  void loadRepo()
})
</script>

<template>
  <section v-if="loaded && next" class="getting-started" data-test="getting-started">
    <button type="button" class="toggle" :aria-expanded="open ? 'true' : 'false'" data-test="getting-started-toggle" @click="open = !open">
      <component :is="open ? ChevronDown : ChevronRight" :size="16" aria-hidden="true" />
      <span class="title">Začínáme</span>
      <span class="progress">{{ doneCount }} / {{ steps.length }} hotovo · další krok: {{ next.title }}</span>
    </button>
    <ol v-if="open" class="steps">
      <li
        v-for="(step, index) in steps"
        :key="step.id"
        class="step"
        :class="{ done: step.done, next: step.id === next.id }"
        :data-step="step.id"
        :data-done="step.done ? 'true' : 'false'"
        data-test="getting-started-step"
      >
        <span class="mark" aria-hidden="true"><Check v-if="step.done" :size="14" /><template v-else>{{ index + 1 }}</template></span>
        <span class="body">
          <strong>{{ step.title }}</strong>
          <span class="hint">{{ step.hint }}</span>
        </span>
        <a v-if="step.id === next.id" :href="step.href" class="go" data-test="getting-started-next">{{ step.action }}</a>
        <a v-else-if="!step.done" :href="step.href" class="link">{{ step.action }}</a>
      </li>
    </ol>
  </section>
</template>

<style scoped>
.getting-started {
  margin: 0 0 18px;
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}

.toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 0;
  border: 0;
  background: none;
  color: var(--text);
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.title {
  font-weight: 700;
}

.progress {
  color: var(--dim);
  font-size: 14px;
}

.steps {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
}

.step {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  border: 1px solid transparent;
  border-radius: 10px;
}

.step.next {
  border-color: var(--blue);
  background: var(--panel-2);
}

.mark {
  display: inline-grid;
  place-items: center;
  flex: none;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--panel-3);
  font-size: 13px;
}

.done .mark {
  background: rgba(74, 222, 128, 0.2);
  color: var(--green);
}

.body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.done .body strong {
  color: var(--dim);
}

.hint {
  color: var(--dim);
  font-size: 14px;
}

.go {
  padding: 5px 12px;
  border: 1px solid rgba(74, 222, 128, 0.55);
  border-radius: 8px;
  color: var(--green);
  font-weight: 700;
  white-space: nowrap;
}

.link {
  color: var(--blue);
  font-size: 14px;
  white-space: nowrap;
}
</style>
