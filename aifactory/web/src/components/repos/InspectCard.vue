<script setup lang="ts">
import { errorText } from '../../lib/format'
// The card of an inspected folder on the Add repository page (POST /api/repos/inspect):
// its repo root, branch, remote, factory state and trace DB, then one action. Adding
// (or syncing a registered repo) writes .factory/ from the library and commits it on base.
import { computed, ref } from 'vue'
import { ApiError, addRepo, type AddRepoResult, type InspectResult, type RepoProblem } from '@/lib/api'
import { problemText } from '@/lib/addRepo'
import { factoryStateText, onboardingText } from '@/lib/repos'
import { repoHref } from '@/lib/router'
import Spinner from '@/components/ui/Spinner.vue'

const props = defineProps<{ inspect: InspectResult }>()
const emit = defineEmits<{ added: [result: AddRepoResult]; reinspect: [path: string] }>()

const adding = ref(false)
const addError = ref<string | null>(null)

const state = computed(() => props.inspect.factory?.state ?? null)
const kind = computed<'problem' | 'registered' | 'add'>(() => {
  if (props.inspect.problem !== null) return 'problem'
  return props.inspect.registered !== null ? 'registered' : 'add'
})
const root = computed(() => props.inspect.root ?? props.inspect.path)
const base = computed(() => props.inspect.factory?.base ?? props.inspect.branch ?? 'base')
/** A registered repo opens on its Backlog once factory is onboarded, else on its Factory tab. */
const openHref = computed(() => props.inspect.registered
  ? repoHref(props.inspect.registered, state.value === 'onboarded' ? 'backlog' : 'factory') : '')

async function add() {
  adding.value = true
  addError.value = null
  try {
    emit('added', await addRepo(root.value))
  } catch (err) {
    if (err instanceof ApiError) {
      const data = (err.data && typeof err.data === 'object' ? err.data : {}) as Partial<RepoProblem>
      addError.value = problemText({ ...data, code: err.code, message: err.message }, props.inspect)
    } else {
      addError.value = errorText(err)
    }
  } finally {
    adding.value = false
  }
}
</script>

<template>
  <article class="inspect-card" data-test="inspect-card" :data-state="inspect.problem ? 'problem' : (state ?? 'unknown')">
    <dl class="rows">
      <template v-if="inspect.root">
        <dt>Kořen repozitáře</dt>
        <dd class="mono" data-test="inspect-root">{{ inspect.root }}</dd>
      </template>
      <template v-else>
        <dt>Složka</dt>
        <dd class="mono" data-test="inspect-path">{{ inspect.path }}</dd>
      </template>
      <template v-if="inspect.branch">
        <dt>Větev</dt>
        <dd class="mono" data-test="inspect-branch">{{ inspect.branch }}</dd>
      </template>
      <template v-if="inspect.root && !inspect.problem">
        <dt>Remote</dt>
        <dd class="mono" data-test="inspect-remote">{{ inspect.remote?.url ?? 'bez remote' }}</dd>
      </template>
      <template v-if="inspect.factory">
        <dt>Factory</dt>
        <dd data-test="inspect-state">{{ factoryStateText(inspect.factory.onboarding_state ?? inspect.factory.state, inspect.factory.onboarding_pr?.id) }}<a v-if="inspect.factory.onboarding_pr" :href="inspect.factory.onboarding_pr.url" target="_blank" rel="noopener"> Otevřít PR</a></dd>
      </template>
      <template v-if="inspect.trace_db">
        <dt>Trace DB</dt>
        <dd class="mono" data-test="inspect-trace-db">{{ inspect.trace_db }}</dd>
      </template>
    </dl>

    <p v-if="inspect.subdir && inspect.root" class="note" data-test="inspect-subdir">
      Použije se kořen repozitáře {{ inspect.root }}.
    </p>

    <p v-if="inspect.factory?.onboarding" class="note" data-test="inspect-onboarding">
      {{ onboardingText(inspect.factory.onboarding) }} · knihovna {{ inspect.factory.library?.name ?? '—' }}
    </p>

    <template v-if="kind === 'problem' && inspect.problem">
      <p class="problem" data-test="inspect-problem">{{ problemText(inspect.problem, inspect) }}</p>
      <button
        v-if="inspect.problem.code === 'linked_worktree' && inspect.problem.main_checkout"
        type="button"
        class="btn"
        data-test="use-main-checkout"
        @click="emit('reinspect', inspect.problem.main_checkout)"
      >
        Použít hlavní checkout
      </button>
    </template>

    <template v-else>
      <p v-if="kind === 'registered'" class="note" data-test="inspect-registered">Repo už je v dashboardu.</p>
      <p class="note" data-test="inspect-install-note">
        {{ kind === 'registered' ? 'Synchronizace' : 'Přidání' }} zapíše do repa .factory z knihovny (existující nahradí), doplní .gitignore a commitne to do {{ base }}.
      </p>
      <p v-if="adding" class="note" data-test="inspect-adding">Zapisuji factory a commituji do {{ base }}…</p>
      <p v-if="addError" class="problem" data-test="inspect-add-error">{{ addError }}</p>
      <div class="actions">
        <template v-if="kind === 'registered'">
          <a :href="openHref" class="btn" data-test="inspect-open">Otevřít</a>
          <button type="button" class="btn ok" :disabled="adding" data-test="inspect-sync" @click="add">
            <Spinner v-if="adding" /> Synchronizovat s knihovnou
          </button>
        </template>
        <button v-else type="button" class="btn ok" :disabled="adding" data-test="inspect-add" @click="add">
          <Spinner v-if="adding" /> Přidat
        </button>
      </div>
    </template>
  </article>
</template>

<style scoped>
.inspect-card {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 12px;
  margin-top: 18px;
  padding: 18px 20px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--surface);
}

.rows {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  gap: 6px 18px;
  width: 100%;
  margin: 0;
}

dt {
  color: var(--dim);
}

dd {
  margin: 0;
  overflow-wrap: anywhere;
}

.note {
  margin: 0;
  color: var(--dim);
}

.warn {
  margin: 0;
  color: var(--amber);
}

.problem {
  margin: 0;
  color: var(--red);
  font-weight: 600;
}

.actions {
  display: flex;
  gap: 10px;
}

.command {
  width: 100%;
  box-sizing: border-box;
  margin: 0;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font-family: var(--mono);
  font-size: 14px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  text-decoration: none;
  cursor: pointer;
}

.btn:disabled {
  cursor: default;
  opacity: 0.7;
}

.btn.ok {
  border-color: rgba(74, 222, 128, 0.55);
  color: var(--green);
  font-weight: 700;
}
</style>
