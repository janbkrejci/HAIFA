<script setup lang="ts">
import { t } from '@/lib/i18n'
import { factoryDiagnostic, factoryErrorText } from '@/lib/factoryMessages'
import { computed, onBeforeUnmount, onMounted, ref, toRaw, watch } from 'vue'
import { ApiError, applyBasePull, applyFactoryPlan, fetchBasePullPlan, fetchFactoryPlan, fetchOverview, type FactoryAction, type FactoryOptions, type FactoryPlan, type FactoryInitPlan, type FactoryRequest, type FactoryResult, type OverviewRunning } from '@/lib/api'
import { installOptions, lastFactoryResult } from '@/lib/factory'
import { useConfirm } from '@/lib/confirm'
import { useLive } from '@/lib/live'
import { repoHref } from '@/lib/router'
import { runningKey, runningLink } from '@/lib/overview'
import { shortSha } from '@/lib/format'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import PlanView from './PlanView.vue'
import InstallForm from './InstallForm.vue'
const props = defineProps<{ action: FactoryAction; repoId: string; remote?: string | null }>()
const emit = defineEmits<{ success: []; busy: [busy: boolean] }>()
const options = ref<FactoryOptions>({})
const target = ref<'base' | 'pr'>('base')
const message = ref('')
const plan = ref<FactoryPlan | null>(null)
const formPlan = ref<FactoryInitPlan | null>(null)
const loading = ref(false)
const applying = ref(false)
const error = ref<unknown>('')
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
const EMPTY_PLAN_TEXT = computed<Record<FactoryAction, string>>(() => ({
  init: t('factoryUi.emptyInit'),
  config_commit: t('factoryUi.emptyConfig'),
  pull: t('factoryUi.emptyPull'),
}))
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
    }
  } catch (e) {
    if (mine !== generation || disposed) return
    error.value = e
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
  const params = { remote: remote.value ?? '', base: plan.value.base, count: plan.value.files.length }
  if (!await ask(() => ({
    title: props.action === 'pull' ? t('factoryUi.confirmPull', params)
      : target.value === 'pr' ? t('factoryUi.confirmPr', params)
      : t(remote.value ? 'factoryUi.confirmPush' : 'factoryUi.confirmCommit', params),
    confirmLabel: t('factoryUi.perform'),
  }))) return
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
    error.value = e
    errorCode.value = e instanceof ApiError ? e.code : ''
    if (errorCode.value === 'plan_changed') {
      await load()
      error.value = new ApiError('plan_changed', '')
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
      <InstallForm v-if="action === 'init' && formPlan" :options="options" @change="change" />
      <label v-if="action !== 'pull'">{{ t('factoryUi.target') }} <SelectMenu :model-value="target" :label="t('factoryUi.target')" :options="[{value:'base',label:'Base'},{value:'pr',label:'PR'}]" data-test="factory-target" @update:model-value="target = $event as 'base' | 'pr'; load()" /></label>
      <label v-if="action !== 'pull'">{{ t('factoryUi.commitMessage') }} <input v-model="message" data-test="factory-message"></label>
    </fieldset>
    <p v-if="loading" role="status">{{ t('factoryUi.recalculating') }}</p>
    <p v-if="error" role="alert" class="error" data-test="operation-error"><template v-if="!plan && errorCode">{{ t('factoryUi.blocker') }} </template>{{ errorCode }}: {{ factoryErrorText(error) }}</p>
    <details v-if="error"><summary>{{ t('factoryUi.technical') }}</summary>{{ factoryDiagnostic(error) }}</details>
    <template v-if="errorCode === 'push_failed'">
      <p>{{ t('factoryUi.unchangedRepo') }}</p>
      <button type="button" data-test="factory-pr" @click="asPr">{{ t('factoryUi.asPr') }}</button>
    </template>
    <p v-if="runsFailed" data-test="factory-runs-failed">{{ t('factoryUi.runsFailed') }}
      <button type="button" data-test="factory-runs-retry" @click="refreshRuns">{{ t('factoryUi.retry') }}</button></p>
    <p v-else-if="!runsKnown">{{ t('factoryUi.runsChecking') }}</p>
    <div v-if="runs.length" data-test="factory-running">
      <p>{{ t('factoryUi.runsWaiting', { count: runs.length }, runs.length) }}</p>
      <a v-for="run in runs" :key="runningKey(run)" :href="runningLink({ id: repoId }, run)">{{ run.run_id ?? run.task_id }} </a>
    </div>
    <PlanView v-if="plan" :plan="plan" :title="t('factoryUi.preview')" data-test="factory-plan">
      <p v-if="plan.action === 'pull'">{{ t('factoryUi.pullToFragment') }} {{ plan.base }} ({{ shortSha(plan.before) }} → {{ shortSha(plan.after) }}{{ t('factoryUi.fromFragment') }} {{ plan.remote }}/{{ plan.base }}</p>
      <p v-else-if="target === 'pr'">{{ t('factoryUi.prCommitFragment') }} {{ plan.base }}</p>
      <p v-else>{{ t('factoryUi.baseCommitFragment') }} {{ plan.base }} ({{ shortSha(plan.base_sha) }} {{ t('factoryUi.newFragment') }}<template v-if="remote">{{ t('factoryUi.pushFragment') }} {{ remote }}/{{ plan.base }}</template></p>
    </PlanView>
    <button type="button" :disabled="disabled" data-test="factory-perform" @click="perform">{{ t(applying ? 'factoryUi.performing' : 'factoryUi.perform') }}</button>
    <p v-if="emptyPlan" data-test="factory-plan-empty">{{ EMPTY_PLAN_TEXT[action] }}</p>
    <div v-if="result" data-test="factory-success">
      <p>{{ t('factoryUi.done') }} {{ result.commit ?? result.after }}</p>
      <details v-for="w in result.warnings" :key="w"><summary>{{ t('factoryUi.warning') }} {{ t('factoryUi.technical') }}</summary>{{ w }}</details>
      <template v-if="result.pr"><a :href="result.pr.url" target="_blank" rel="noopener">{{ t('factoryUi.openPr') }}</a><p>{{ t('factoryUi.waitMerge') }}</p></template>
      <a :href="repoHref(repoId,'backlog')">{{ t('factoryUi.openBacklog') }}</a>
    </div>
    <ConfirmDialog v-bind="dialog" @confirm="confirm" @cancel="cancel" />
  </section>
</template>
<style scoped>
.operation { margin: 20px 0; padding: 18px; border: 1px solid var(--border); border-radius: 10px; }
fieldset { border: 0; padding: 0; }label { display: inline-flex; gap: 8px; margin: 10px; }button, input, select { padding: 6px 12px; background: var(--panel-2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; }button:disabled { opacity: .5; }.error { color: var(--red); }
</style>
