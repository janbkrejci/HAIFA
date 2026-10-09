<script setup lang="ts">
import { errorText } from '../../lib/format'
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ApiError, applyOnboarding, previewOnboarding, type FactoryResult } from '@/lib/api'
import { type OnboardingPlan } from '@/lib/onboarding'
import { applyLibrary, previewLibrary, type LibraryPlan } from '@/lib/library'
import { useConfirm } from '@/lib/confirm'
import { repoHref } from '@/lib/router'
import { lastFactoryResult, planCodeText } from '@/lib/factory'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import PlanView from './PlanView.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import FactoryOperation from './FactoryOperation.vue'
const props = defineProps<{ repoId: string; action: 'onboard' | 'adopt'; disabled?: boolean }>()
const emit = defineEmits<{ busy: [value: boolean]; success: [] }>()
const plan = ref<OnboardingPlan | null>(null)
const error = ref('')
const code = ref('')
const cloneRemote = ref<string | null>(null)
const clonePlan = ref<LibraryPlan | null>(null)
const pulling = ref(false)
const loading = ref(false)
const busy = ref(false)
const result = ref<(FactoryResult & { library_commit?: string }) | null>(null)
const target = ref<'base' | 'pr'>('base')
const message = ref('')
const { dialog, ask, confirm, cancel } = useConfirm()
let generation = 0
let disposed = false
const changes = computed(() => plan.value?.library_plan ?? plan.value?.plan)
const changedItems = computed(() => changes.value?.items.filter(item => item.action !== 'unchanged') ?? [])
const blockers = computed(() => plan.value?.blockers ?? [])
const remoteBlocked = computed(() => code.value === 'onboarded_in_remote' || blockers.value.some(b => b.code === 'onboarded_in_remote'))
const pending = computed(() => code.value === 'onboarding_pending' || blockers.value.some(b => b.code === 'onboarding_pending'))
const TARGET_OPTIONS = [{ value: 'base', label: 'Commit do base' }, { value: 'pr', label: 'Pull request' }]
const reportGroups = computed(() => [...new Set(plan.value?.report?.map(r => r.code))].map(code => ({ code, rows: plan.value?.report?.filter(r => r.code === code) ?? [] })))
const disabled = computed(() => props.disabled || loading.value || busy.value || !!result.value || !plan.value || !!blockers.value.length || (props.action === 'adopt' ? !changedItems.value.length : !plan.value.files?.length))
async function load() {
  const mine = ++generation
  cancel(); loading.value = true; error.value = ''; code.value = ''; plan.value = null; cloneRemote.value = null
  try {
    const data = await previewOnboarding(props.repoId, props.action, target.value)
    if (!disposed && mine === generation) plan.value = data
  } catch (e) {
    if (disposed || mine !== generation) return
    error.value = errorText(e)
    if (e instanceof ApiError) {
      code.value = e.code
      const data = e.data as OnboardingPlan & { remote?: string }
      if (data?.digest) plan.value = data
      if (code.value === 'library_missing' && typeof data?.remote === 'string') cloneRemote.value = data.remote
    }
  } finally { if (!disposed && mine === generation) loading.value = false }
}
async function perform() {
  if (disabled.value || !plan.value) return
  const mine = generation
  const snapshot = { digest: plan.value.digest, target: target.value, message: message.value }
  const title = props.action === 'adopt'
    ? `Doplnit ${changedItems.value.length} položek do knihovny ${plan.value.library?.name}?`
    : `Commitnout ${changedItems.value.length} položek do knihovny ${plan.value.library?.name ?? '—'} a pushnout, pak commitnout ${plan.value.files?.length ?? 0} souborů do ${plan.value.base} a ${target.value === 'pr' ? 'otevřít PR' : `pushnout na ${plan.value.remote?.name ?? 'bez remote'}`}? adws/ zůstane beze změny.`
  if (!await ask({ title, confirmLabel: 'Provést' }) || disposed || mine !== generation || disabled.value) return
  busy.value = true; emit('busy', true)
  try {
    result.value = await applyOnboarding(props.repoId, props.action, snapshot.target, snapshot.digest, snapshot.message)
    lastFactoryResult.value = { repoId: props.repoId, result: result.value }
    window.dispatchEvent(new Event('factory-applied')); emit('success')
  } catch (e) {
    await load()
    error.value = e instanceof ApiError && e.code === 'plan_changed' ? 'Plán se změnil. Zkontroluj nový náhled.' : errorText(e)
  } finally { busy.value = false; emit('busy', false) }
}
async function clone() {
  if (!cloneRemote.value || busy.value || props.disabled) return
  const request = { action: 'clone' as const, options: { url: cloneRemote.value } }
  busy.value = true; emit('busy', true)
  try {
    clonePlan.value = await previewLibrary(request)
    if (clonePlan.value.blockers.length) return
    if (!await ask({ title: `Naklonovat knihovnu z ${cloneRemote.value}?`, confirmLabel: 'Naklonovat' })) return
    await applyLibrary(request, clonePlan.value.digest)
    clonePlan.value = null; await load(); window.dispatchEvent(new Event('factory-applied')); emit('success')
  } catch (e) { error.value = errorText(e) }
  finally { busy.value = false; emit('busy', false) }
}
onMounted(load)
onBeforeUnmount(() => { disposed = true; ++generation; cancel() })
</script>
<template>
  <section class="onboarding" data-test="onboarding-panel">
    <h2>{{ action === 'adopt' ? 'Převzetí' : 'Onboarding — jednou pro repo' }}</h2>
    <p v-if="loading" role="status">Načítám náhled…</p>
    <p v-if="error" role="alert"><template v-if="code">{{ planCodeText(code) }}: </template>{{ error }}</p>
    <p v-if="remoteBlocked" data-test="onboarding-state">Onboardováno na remote</p>
    <button type="button" v-if="remoteBlocked" :disabled="busy || props.disabled" @click="pulling = true">Stáhnout konfiguraci z base, pak převzít</button>
    <FactoryOperation v-if="pulling" action="pull" :repo-id="repoId" @busy="busy = $event; emit('busy', $event)" @success="emit('success')" />
    <p v-if="pending" data-test="onboarding-state">Čeká v PR <template v-if="plan?.pending_pr">#{{ plan.pending_pr.id }} </template><a v-if="plan?.pending_pr?.url" :href="plan.pending_pr.url" target="_blank" rel="noopener">Otevřít PR onboardingu</a><a v-else :href="repoHref(repoId, 'review')">Otevřít PR onboardingu</a></p>
    <button type="button" v-if="cloneRemote" :disabled="busy || props.disabled" data-test="adopt-clone" @click="clone">Naklonovat knihovnu z {{ cloneRemote }}</button>
    <PlanView v-if="clonePlan" :plan="{ blockers: clonePlan.blockers }" />
    <template v-if="plan">
      <p v-if="plan.library?.matches === false" role="alert">Jiná knihovna: {{ plan.library.name }}; repo používá {{ plan.manifest_library?.name }}.</p>
      <fieldset v-if="action === 'onboard'" :disabled="busy || !!result">
        <label>Cíl <SelectMenu v-model="target" label="Cíl" :options="TARGET_OPTIONS" @update:model-value="load" /></label>
        <label>Zpráva commitu <input v-model="message" @input="cancel" /></label>
      </fieldset>
      <PlanView :plan="{ blockers }" />
      <div data-test="onboarding-plan">
        <section data-test="onboarding-library"><h3>Knihovna — {{ plan.library?.name }}</h3>
          <PlanView :plan="{ items: changedItems }" />
          <p v-if="!changedItems.length">Bez nových položek a verzí.</p>
        </section>
        <section data-test="onboarding-repo"><h3>Repozitář</h3>
          <PlanView :plan="{ files: plan.files }" />
          <p v-if="action === 'adopt'">Repozitář zůstane beze změny.</p>
        </section>
        <section data-test="onboarding-report"><h3>Zpráva</h3>
          <article v-for="group in reportGroups" :key="group.code"><h4>{{ planCodeText(group.code) }}</h4><p v-for="(row, i) in group.rows" :key="i">{{ row.subject }}: {{ row.message }} {{ row.detail }} {{ row.version }}</p></article>
          <p v-for="item in plan.items && Array.isArray(plan.items) ? plan.items : []" :key="`${item.type}/${item.name}`">{{ item.type }}/{{ item.name }}: {{ planCodeText(item.state) }} · {{ planCodeText(item.adopt) }} {{ item.fix }}</p>
          <PlanView :plan="{ warnings: plan.warnings, envelopeWarnings: plan.envelopeWarnings }" />
        </section>
      </div>
      <button type="button" :disabled="disabled" data-test="onboarding-perform" @click="perform">{{ busy ? 'Provádím…' : action === 'adopt' ? 'Doplnit knihovnu' : 'Provést' }}</button>
      <p v-if="action === 'adopt' && !changedItems.length">Knihovna nevyžaduje doplnění.</p>
    </template>
    <div v-if="result" data-test="onboarding-success"><p>Commit knihovny: {{ result.library_commit ?? 'beze změny' }}</p><p v-if="action === 'onboard'">Commit repa: {{ result.commit }}</p><p v-for="warning in result.warnings" :key="warning">{{ warning }}</p><a v-if="result.pr" :href="result.pr.url" target="_blank" rel="noopener">Otevřít PR</a></div>
    <ConfirmDialog v-bind="dialog" @confirm="confirm" @cancel="cancel" />
  </section>
</template>
<style scoped>
.onboarding { background: var(--surface); padding: 18px; margin: 18px 0; border: 1px solid var(--border); border-radius: 10px; }
button, input { padding: 6px 12px; background: var(--panel-2); color: var(--text); border: 1px solid var(--border); border-radius: 6px; } button:disabled { opacity: .5; }
fieldset { border: 0; } label { display: inline-flex; gap: 8px; margin: 8px; } article { margin: 12px 0; }
</style>
