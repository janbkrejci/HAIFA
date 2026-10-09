<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue'
import { ApiError, applyBasePull, applyFactoryPlan, fetchBasePullPlan, fetchFactoryPlan, fetchOverview, type FactoryAction, type FactoryOptions, type FactoryPlan, type FactoryInitPlan, type FactoryRequest, type FactoryResult, type OverviewRunning } from '@/lib/api'
import { installOptions, lastFactoryResult } from '@/lib/factory'
import { useConfirm } from '@/lib/confirm'
import { useLive } from '@/lib/live'
import { repoHref } from '@/lib/router'
import { errorText, plural, shortSha } from '@/lib/format'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import PlanView from './PlanView.vue'
import InstallForm from './InstallForm.vue'
import UpdateChoices from './UpdateChoices.vue'
const props = defineProps<{ action: FactoryAction; repoId: string; remote?: string | null }>()
const emit = defineEmits<{ success: []; busy: [busy: boolean] }>()
const options = ref<FactoryOptions>({})
const target = ref<'base' | 'pr'>('base')
const message = ref('')
const plan = ref<FactoryPlan | null>(null)
const formPlan = ref<FactoryInitPlan | null>(null)
const loading = ref(false)
const applying = ref(false)
const error = ref('')
const errorCode = ref('')
const result = ref<FactoryResult | null>(null)
const runs = ref<OverviewRunning[]>([])
const runsKnown = ref(false)
/** The run state could not be verified (no answer, or the repo is unreadable): writes stay off until a retry. */
const runsFailed = ref(false)
const { dialog, ask, confirm, cancel } = useConfirm()
let generation = 0
let runGeneration = 0
let disposed = false
const disabled = computed(() => loading.value || applying.value || !plan.value || !!plan.value.blockers.length || (plan.value.action === 'pull' ? plan.value.before === plan.value.after : !plan.value.files.length) || !runsKnown.value || !!runs.value.length || !!result.value)
const remote = computed(() => plan.value?.remote !== undefined ? plan.value.remote : props.remote)
const EMPTY_PLAN_TEXT: Record<FactoryAction, string> = {
  init: 'Instalace nemá co zapsat.',
  update: 'Vše je aktuální, z knihovny není co převzít.',
  config_commit: 'Konfigurace je commitnutá, není co commitnout.',
  pull: 'Konfigurace odpovídá base, není co stáhnout.',
}
const emptyPlan = computed(() => !!plan.value && (plan.value.action === 'pull' ? plan.value.before === plan.value.after : !plan.value.files?.length))
function requestBody() {
  if (props.action === 'pull') throw new Error('pull has a separate API')
  return { action: props.action, options: options.value, target: target.value }
}
async function load(initial = false) {
  const mine = ++generation
  cancel()
  loading.value = true
  error.value = ''
  errorCode.value = ''
  try {
    const next = props.action === 'pull' ? await fetchBasePullPlan(props.repoId) : await fetchFactoryPlan(requestBody(), props.repoId)
    if (mine !== generation || disposed) return
    plan.value = next
    if (next.action === 'init') {
      formPlan.value = next
      if (initial) options.value = installOptions(next)
      // Workflows can add required agents. Preserve every existing override.
      for (const name of next.added_agents ?? []) {
        if (!options.value.agents?.includes(name)) options.value.agents?.push(name)
        if (next.bindings?.[name] && !options.value.bind?.[name]) {
          options.value.bind ??= {}
          options.value.bind[name] = next.bindings[name]!
        }
      }
    }
  } catch (e) {
    if (mine !== generation || disposed) return
    error.value = errorText(e)
    errorCode.value = e instanceof ApiError ? e.code : ''
    const data = e instanceof ApiError ? e.data as FactoryPlan | null : null
    plan.value = data?.digest && Array.isArray(data.files) && Array.isArray(data.blockers) ? data : null
  } finally {
    if (mine === generation && !disposed) loading.value = false
  }
}
function change(value: FactoryOptions) {
  options.value = value
  result.value = null
  void load()
}
async function refreshRuns() {
  const mine = ++runGeneration
  runsKnown.value = false
  runsFailed.value = false
  cancel()
  try {
    const overview = await fetchOverview()
    if (mine !== runGeneration || disposed) return
    const repo = overview.repos.find(r => r.id === props.repoId)
    if (repo && !['error','timeout','missing','not_git'].includes(repo.state)) {
      runs.value = repo.running.filter(r => r.process !== 'ended')
      runsKnown.value = true
    } else runsFailed.value = true
  } catch {
    // An unverifiable run state disables writes.
    if (mine === runGeneration && !disposed) runsFailed.value = true
  }
}
async function perform() {
  if (disabled.value || !plan.value) return
  const mine = generation
  const snapshot: FactoryRequest & { digest: string; message: string } = structuredClone({ action: props.action as FactoryRequest['action'], options: toRaw(options.value), target: target.value, digest: plan.value.digest, message: message.value })
  const title = props.action === 'pull' ? `Stáhnout konfiguraci z ${remote.value}/${plan.value.base}?`
    : target.value === 'pr' ? `Commitnout ${plan.value.files.length} souborů a otevřít PR do ${plan.value.base}?`
    : `Commitnout ${plan.value.files.length} souborů do ${plan.value.base}${remote.value ? ` a pushnout na ${remote.value}` : ''}?`
  if (!await ask({ title, confirmLabel: 'Provést' })) return
  if (disposed || mine !== generation || disabled.value) return
  applying.value = true
  emit('busy', true)
  error.value = ''
  errorCode.value = ''
  try {
    const answer = props.action === 'pull' ? await applyBasePull(snapshot.digest, props.repoId) : await applyFactoryPlan(snapshot, props.repoId)
    if (disposed) return
    result.value = answer
    lastFactoryResult.value = { repoId: props.repoId, result: answer, action: props.action }
    window.dispatchEvent(new Event('factory-applied'))
    emit('success')
    void refreshRuns()
  } catch (e) {
    if (disposed) return
    error.value = errorText(e)
    errorCode.value = e instanceof ApiError ? e.code : ''
    if (errorCode.value === 'plan_changed') {
      await load()
      error.value = 'Plán se změnil. Zkontroluj nový náhled a znovu jej potvrď.'
    }
    if (errorCode.value === 'run_in_progress') { await refreshRuns(); await load() }
  } finally {
    applying.value = false
    emit('busy', false)
  }
}
function asPr() { target.value = 'pr'; void load() }
watch(message, cancel)
useLive({ trace: e => { if(e.runs_changed) void refreshRuns() }, resync: () => { void refreshRuns(); void load() } })
onMounted(() => { void load(true); void refreshRuns(); window.addEventListener('focus', refreshRuns) })
onBeforeUnmount(() => { disposed = true; ++generation; ++runGeneration; cancel(); window.removeEventListener('focus', refreshRuns) })
</script>
<template>
  <section class="operation" data-test="factory-operation">
    <fieldset :disabled="applying || !!result">
      <InstallForm v-if="action === 'init' && formPlan" :options="options" :plan="formPlan" @change="change" />
      <UpdateChoices v-if="action === 'update' && plan?.action === 'update'" :plan="plan" :options="options" @change="change" />
      <label v-if="action !== 'pull'">Cíl <SelectMenu :model-value="target" label="Cíl" :options="[{value:'base',label:'Base'},{value:'pr',label:'PR'}]" data-test="factory-target" @update:model-value="target = $event as 'base' | 'pr'; load()" /></label>
      <label v-if="action !== 'pull'">Zpráva commitu <input v-model="message" data-test="factory-message"></label>
    </fieldset>
    <p v-if="loading" role="status">Přepočítávám plán…</p>
    <p v-if="error" role="alert" class="error" data-test="operation-error"><template v-if="!plan && errorCode">Blokátor </template>{{ errorCode }}: {{ error }}</p>
    <template v-if="errorCode === 'push_failed'">
      <p>V repozitáři se nic nezměnilo</p>
      <button type="button" data-test="factory-pr" @click="asPr">Otevřít jako PR</button>
    </template>
    <p v-if="runsFailed" data-test="factory-runs-failed">Stav běhů se nepodařilo ověřit, zápis je zakázaný.
      <button type="button" data-test="factory-runs-retry" @click="refreshRuns">Zkusit znovu</button></p>
    <p v-else-if="!runsKnown">Stav běhů se ověřuje, zápis je zakázaný.</p>
    <div v-if="runs.length" data-test="factory-running">
      <p>V repu běží {{ runs.length }} {{ plural(runs.length, 'běh', 'běhy', 'běhů') }}, počká se, až {{ runs.length === 1 ? 'doběhne' : 'doběhnou' }}.</p>
      <a v-for="run in runs" :key="run.run_id" :href="repoHref(repoId,'runs',run.run_id)">{{ run.run_id }} </a>
    </div>
    <PlanView v-if="plan" :plan="plan" title="Náhled plánu" data-test="factory-plan">
      <p v-if="plan.action === 'pull'">Stáhnout konfiguraci do {{ plan.base }} ({{ shortSha(plan.before) }} → {{ shortSha(plan.after) }}) z {{ plan.remote }}/{{ plan.base }}</p>
      <p v-else-if="target === 'pr'">1 commit na nové větvi a otevření PR do {{ plan.base }}</p>
      <p v-else>1 commit na {{ plan.base }} ({{ shortSha(plan.base_sha) }} → nový)<template v-if="remote">, push na {{ remote }}/{{ plan.base }}</template></p>
    </PlanView>
    <button type="button" :disabled="disabled" data-test="factory-perform" @click="perform">{{ applying ? 'Provádím…' : 'Provést' }}</button>
    <p v-if="emptyPlan" data-test="factory-plan-empty">{{ EMPTY_PLAN_TEXT[action] }}</p>
    <div v-if="result" data-test="factory-success">
      <p>Hotovo: {{ result.commit ?? result.after }}</p>
      <p v-for="w in result.warnings" :key="w">{{ w }}</p>
      <template v-if="result.pr"><a :href="result.pr.url" target="_blank" rel="noopener">Otevřít PR</a><p>Běhy počkají na merge. Po merge použij Stáhnout konfiguraci z base.</p></template>
      <a :href="repoHref(repoId,'backlog')">Otevřít backlog</a>
    </div>
    <ConfirmDialog v-bind="dialog" @confirm="confirm" @cancel="cancel" />
  </section>
</template>
<style scoped>
.operation { margin: 20px 0; padding: 18px; border: 1px solid var(--border); border-radius: 10px; }
fieldset { border: 0; padding: 0; }label { display: inline-flex; gap: 8px; margin: 10px; }button, input, select { padding: 6px 12px; background: var(--panel-2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; }button:disabled { opacity: .5; }.error { color: var(--red); }
</style>
