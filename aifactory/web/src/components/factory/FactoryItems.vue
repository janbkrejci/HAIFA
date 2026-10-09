<script setup lang="ts">
import { errorText } from '../../lib/format'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError, applyFactoryItem, fetchFactoryItemDiff, fetchFactoryItems, fetchFactoryRoster, fetchRepos, previewFactoryItem,
  type FactoryItemAction, type FactoryItemDiff, type FactoryItemOptions, type FactoryItemPlan, type FactoryItemRequest,
  type FactoryItemType, type FactoryRepoItem, type FactoryRoster, type FactoryRosterAgent, type FactoryOptions, type FactoryUpdatePlan, type RepoItem } from '@/lib/api'
import { fetchLibrary, ITEM_TABS, stateText, type LibraryItem } from '@/lib/library'
import UpdateChoices from './UpdateChoices.vue'
import PlanView from './PlanView.vue'
import { planCodeText } from '@/lib/factory'
import DiffContent from '@/components/review/DiffContent.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'

const props = defineProps<{ repoId: string; disabled?: boolean }>()
const emit = defineEmits<{ busy: [value: boolean]; success: [] }>()
const items = ref<FactoryRepoItem[]>([])
const roster = ref<FactoryRoster>({ agents: [], workflow_tasks: {} })
const library = ref<LibraryItem[]>([])
const repos = ref<RepoItem[]>([])
const destinationRoster = ref<FactoryRosterAgent[]>([])
const bindingAgents = computed(() => active.value === 'copy' ? destinationRoster.value : roster.value.agents)
const loading = ref(false)
const error = ref('')
const result = ref('')
const active = ref<FactoryItemAction | 'copy' | 'diff' | null>(null)
const selected = ref<FactoryRepoItem | null>(null)
const type = ref<FactoryItemType>('agent')
const name = ref('')
const slot = ref('')
const agent = ref('')
const destination = ref('')
const harness = ref('claude')
const model = ref('')
const thinking = ref('')
const target = ref<'base' | 'pr'>('base')
const to = ref<'manifest' | 'head'>('manifest')
const message = ref('')
const plan = ref<FactoryItemPlan | null>(null)
const reviewed = ref<{ body: FactoryItemRequest; repo: string } | null>(null)
const diff = ref<FactoryItemDiff | null>(null)
const busy = ref(false)
const confirm = ref(false)
const updateOptions = ref<FactoryOptions>({})
const copyingAdd = ref(false)
let generation = 0
const labels = { diff: 'Diff', update: 'Aktualizovat', export: 'Exportovat', revert: 'Vrátit', remove: 'Odebrat', copy: 'Kopírovat do…', add: 'Přidat z knihovny…' }
const actions = ['diff', 'update', 'export', 'revert', 'remove', 'copy'] as const
const fixes: Record<string, string> = {
  slot_taken: 'Vyber jiný slot.', in_use: 'Nejprve odeber vazby agentů, workflow nebo tasků backlogu.',
  library_changed_since: 'Aktualizuj položku nebo exportuj pod novým názvem.', run_in_progress: 'Počkej na dokončení běhu.',
  plan_changed: 'Znovu načti a zkontroluj plán.', dirty_paths: 'Commitni konfiguraci a znovu načti plán.',
}
const blockers = ref<{ code: string; message: string; fix?: string }[]>([])
const available = computed(() => library.value.filter(i => i.type === type.value))
const typeOptions = ITEM_TABS.map(tab => ({ value: tab.type, label: tab.label }))
const itemOptions = computed(() => [
  { value: '', label: 'Vyber položku' },
  ...available.value.map(i => ({ value: i.name, label: i.name })),
  ...(active.value === 'copy' && name.value && !available.value.some(i => i.name === name.value)
    ? [{ value: name.value, label: name.value }] : []),
])
const agentOptions = computed(() => [{ value: '', label: 'Bez vazby' }, ...bindingAgents.value.map(a => ({ value: a.name, label: a.name }))])
const repoOptions = computed(() => [{ value: '', label: 'Vyber repo' }, ...repos.value.map(r => ({ value: r.id, label: r.name }))])
const revertOptions = [{ value: 'manifest', label: 'Verzi manifestu' }, { value: 'head', label: 'Aktuální knihovnu' }]
const targetOptions = [{ value: 'base', label: 'Commit do base' }, { value: 'pr', label: 'Pull request' }]
const needsExport = computed(() => selected.value && ['local', 'modified', 'diverged', 'unknown'].includes(selected.value.state))
const inputMode = computed(() => active.value === 'add' || (active.value === 'copy' && copyingAdd.value))
const canPreview = computed(() => (!inputMode.value || !!name.value) && (active.value !== 'copy' || !!destination.value))
function binding(item: FactoryRepoItem): FactoryRosterAgent | undefined { return roster.value.agents.find(a => a.name === item.name) }
async function load() {
  const mine = ++generation
  loading.value = true; error.value = ''
  const results = await Promise.allSettled([fetchFactoryItems(props.repoId), fetchFactoryRoster(props.repoId), fetchLibrary(), fetchRepos()])
  if (mine !== generation) return
  const [i, r, l, rs] = results
  if (i.status === 'fulfilled') items.value = i.value.items
  if (r.status === 'fulfilled') roster.value = r.value
  if (l.status === 'fulfilled') library.value = l.value.items ?? []
  if (rs.status === 'fulfilled') repos.value = rs.value.repos.filter(r => r.id !== props.repoId && r.status === 'ok')
  error.value = results.filter(r => r.status === 'rejected').map(r => String(r.reason)).join('; ')
  loading.value = false
}
function invalidate() { plan.value = null; reviewed.value = null; blockers.value = []; confirm.value = false }
watch([type, name, slot, agent, destination, harness, model, thinking, target, to], invalidate)
watch(type, () => { name.value = ''; slot.value = ''; agent.value = '' }, { flush: 'sync' })
watch(destination, async id => {
  destinationRoster.value = []; agent.value = ''
  if (!id) return
  try {
    const data = await fetchFactoryRoster(id)
    if (destination.value === id) destinationRoster.value = data.agents
  } catch (e) { if (destination.value === id) error.value = errorText(e) }
})
watch(active, value => emit('busy', !!value))
function open(action: typeof active.value, item: FactoryRepoItem | null = null) {
  if (busy.value || props.disabled) return
  invalidate(); error.value = ''; result.value = ''; diff.value = null
  active.value = action; selected.value = item; copyingAdd.value = false
  type.value = item?.type ?? 'agent'; name.value = item?.name ?? ''; slot.value = ''; agent.value = ''; destination.value = ''
  const b = item ? binding(item) : undefined
  harness.value = b?.harness ?? 'claude'; model.value = b?.model ?? ''; thinking.value = b?.thinking ?? ''
  message.value = ''; target.value = 'base'; updateOptions.value = {}
  if (action === 'diff' && item) void showDiff(item)
  if (action === 'copy') {
    name.value = item?.item ?? item?.name ?? ''
    copyingAdd.value = !needsExport.value
  }
}
async function showDiff(item: FactoryRepoItem) {
  busy.value = true
  try { diff.value = await fetchFactoryItemDiff(item, props.repoId) }
  catch (e) { error.value = errorText(e) }
  finally { busy.value = false }
}
function request(): { body: FactoryItemRequest; repo: string } {
  let action = active.value as FactoryItemAction
  let repo = props.repoId
  let options: FactoryItemOptions = { type: type.value, name: selected.value?.name ?? name.value }
  if (active.value === 'copy') {
    action = copyingAdd.value ? 'add' : 'export'
    if (copyingAdd.value) repo = destination.value
  }
  if (action === 'add') options = { type: type.value, name: name.value,
    ...(slot.value ? { slot: slot.value } : {}), ...(agent.value ? { agent: agent.value } : {}),
    ...(type.value === 'agent' ? { harness: harness.value, ...(model.value ? { model: model.value } : {}), ...(thinking.value ? { thinking: thinking.value } : {}) } : {}) }
  if (action === 'export' && slot.value) options.slot = slot.value
  if (action === 'revert') options.to = to.value
  if (action === 'update') options = { item: [`${type.value}/${selected.value!.name}`], ...updateOptions.value }
  return { body: { action, options, target: active.value === 'copy' && !copyingAdd.value ? 'base' : target.value }, repo }
}
async function changeUpdate(options: FactoryOptions) {
  updateOptions.value = options
  await preview()
}
async function preview() {
  if (!canPreview.value || busy.value) return
  invalidate(); error.value = ''; busy.value = true
  try {
    const req = request()
    plan.value = await previewFactoryItem(req.body, req.repo)
    reviewed.value = req; blockers.value = plan.value.blockers ?? []
  } catch (e) {
    if (e instanceof ApiError) {
      blockers.value = [{ code: e.code, message: e.message }]
      const data = e.data as FactoryItemPlan | null
      if (data?.digest && Array.isArray(data.files) && Array.isArray(data.blockers)) plan.value = data
    } else error.value = errorText(e)
  } finally { busy.value = false }
}
async function apply() {
  if (busy.value || !plan.value || !reviewed.value || blockers.value.length) return
  confirm.value = false; busy.value = true; error.value = ''
  const req = reviewed.value
  try {
    const done = await applyFactoryItem(req.body, plan.value.digest, message.value, req.repo)
    result.value = done.pr?.url ?? done.commit ?? done.after ?? 'Hotovo'
    invalidate()
    if (active.value === 'copy' && !copyingAdd.value) {
      name.value = slot.value || selected.value!.item || selected.value!.name
      slot.value = ''; copyingAdd.value = true
      result.value = 'Export dokončen. Zkontroluj druhý plán pro cílové repo.'
    } else { active.value = null }
    await load(); emit('success')
  } catch (e) {
    invalidate()
    if (e instanceof ApiError) blockers.value = [{ code: e.code, message: e.message }]
    else error.value = errorText(e)
  } finally { busy.value = false }
}
onMounted(load)
onBeforeUnmount(() => { ++generation; emit('busy', false) })
defineExpose({ reload: load })
</script>

<template>
  <section data-test="factory-items" class="items">
    <div class="toolbar"><h2>Položky repa</h2><button :disabled="disabled || busy || loading || !!active" data-test="item-add" @click="open('add')">Přidat z knihovny…</button><button :disabled="busy || !!active" @click="load">Obnovit položky</button></div>
    <p v-if="loading">Načítám položky…</p><p v-if="error" role="alert">{{ error }}</p><p v-if="result" data-test="item-result">{{ result }}</p>
    <section v-for="tab in ITEM_TABS" :key="tab.type">
      <h3>{{ tab.label }}</h3>
      <div class="table"><table :data-test="`items-${tab.type}`"><thead><tr><th>Slot</th><th>Položka knihovny / stav</th>
        <template v-if="tab.type === 'agent'"><th>Purpose · vlastní knihovna</th><th>Prompty · vlastní knihovna</th><th>Harness</th><th>Model</th><th>Přemýšlení</th><th>Skilly</th><th>Rozšíření</th><th>Writes</th></template>
        <th v-if="tab.type === 'workflow'">Tasky backlogu</th><th>Akce</th></tr></thead>
        <tbody><tr v-for="item in items.filter(i => i.type === tab.type)" :key="item.name" :data-test="`item-${item.type}-${item.name}`">
          <td>{{ item.name }}</td><td>{{ item.item ?? '—' }} <span :data-state="item.state">{{ stateText(item.state) }}</span></td>
          <template v-if="tab.type === 'agent'">
            <td>{{ binding(item)?.purpose ?? '—' }}</td><td>{{ item.item ?? item.name }} · knihovna</td>
            <td>{{ binding(item)?.harness ?? '—' }}</td><td>{{ binding(item)?.model ?? '—' }}</td><td>{{ binding(item)?.thinking ?? '—' }}</td>
            <td>{{ binding(item)?.skills?.join(', ') || '—' }}</td><td>{{ binding(item)?.extensions?.join(', ') || '—' }}</td><td>{{ binding(item)?.writes?.join(', ') || '—' }}</td>
          </template>
          <td v-if="tab.type === 'workflow'">{{ roster.workflow_tasks[item.name] ?? 0 }}</td>
          <td class="row-actions"><button v-for="action in actions" :key="action" :data-test="`item-${action}`" :disabled="disabled || busy || !!active" @click="open(action, item)">{{ labels[action] }}</button></td>
        </tr></tbody></table></div><p v-if="!items.some(i => i.type === tab.type)">Bez položek</p>
    </section>
    <section v-if="active" class="operation" data-test="item-operation">
      <h3>{{ labels[active] }} <template v-if="active === 'copy'">· {{ copyingAdd ? '2. Přidání do cílového repa' : '1. Export do knihovny' }}</template></h3>
      <button :disabled="busy" data-test="item-close" @click="active = null; invalidate()">Zavřít</button>
      <template v-if="active === 'diff'">
        <section v-for="side in (['manifest', 'head'] as const)" :key="side"><h4>Proti {{ side }}</h4><template v-if="diff"><p v-if="!diff[side].available">Nedostupné: {{ diff[side].reason }}</p><p v-else-if="!diff[side].files.length">Žádné změny</p><details v-for="f in diff[side].files" :key="f.path"><summary>{{ f.path }}</summary><DiffContent :patch="f.diff" :binary="f.binary" /></details></template></section>
      </template>
      <form v-else @submit.prevent="preview">
        <fieldset :disabled="busy">
          <template v-if="inputMode"><label>Typ<SelectMenu v-model="type" data-test="item-type" label="Typ" :options="typeOptions" :disabled="busy || active === 'copy'" /></label>
            <label>Položka<SelectMenu v-model="name" data-test="item-name" label="Položka" :options="itemOptions" :disabled="busy || active === 'copy'" /></label>
          </template>
          <label v-if="(inputMode && ['agent','workflow'].includes(type)) || (['export', 'copy'].includes(active) && !copyingAdd && ['agent','workflow'].includes(type))">{{ inputMode ? 'Slot' : 'Nová položka (prázdné = další verze)' }}<input v-model="slot" data-test="item-slot" /></label>
          <label v-if="inputMode && ['skill','extension'].includes(type)">Vazba na agenta<SelectMenu v-model="agent" data-test="item-agent" label="Vazba na agenta" :options="agentOptions" :disabled="busy" /></label>
          <template v-if="inputMode && type === 'agent'"><label>Harness<input v-model="harness" /></label><label>Model<input v-model="model" /></label><label>Přemýšlení<input v-model="thinking" /></label></template>
          <label v-if="active === 'copy'">Cílové repo<SelectMenu v-model="destination" data-test="item-destination" label="Cílové repo" :options="repoOptions" :disabled="busy" /></label>
          <label v-if="active === 'revert'">Vrátit na<SelectMenu v-model="to" data-test="item-revert-to" label="Vrátit na" :options="revertOptions" :disabled="busy" /></label>
          <label>Cíl<SelectMenu v-model="target" data-test="item-target" label="Cíl" :options="targetOptions" :disabled="busy || active === 'copy' && !copyingAdd" /></label>
          <label>Zpráva commitu<input v-model="message" data-test="item-message" /></label>
          <button data-test="item-preview" :disabled="busy || !canPreview">Náhled plánu</button>
        </fieldset>
      </form>
      <template v-if="plan"><p>Uzávěr závislostí</p><ul><li v-for="(i, index) in [...(plan.added ?? []), ...(plan.kept ?? [])]" :key="index">{{ i.type }}/{{ i.name }}</li></ul>
        <p>Repo: {{ reviewed?.repo }} · {{ reviewed?.body.target === 'pr' ? 'Pull request' : 'Commit do base' }} · {{ plan.base }}</p>
        <PlanView :plan="{ ...plan, blockers: [] }" collapsed data-test="library-plan" />
        <fieldset v-if="plan.update" :disabled="busy"><UpdateChoices :plan="{ ...plan, action: 'update', update: plan.update } as FactoryUpdatePlan" :options="updateOptions" @change="changeUpdate" /></fieldset>
        <template v-if="plan.library_plan"><h4>Export do knihovny</h4><PlanView :plan="plan.library_plan" collapsed /></template>
        <template v-for="i in plan.update?.items ?? []" :key="i.type + i.name"><details v-for="f in i.files" :key="f.file"><summary>{{ f.file }}</summary><DiffContent :patch="f.diff" /><h4>Lokální změny</h4><DiffContent :patch="f.ours_diff" /><h4>Změny knihovny</h4><DiffContent :patch="f.theirs_diff" /></details></template>
      </template>
      <p v-for="b in blockers" :key="b.code" role="alert">{{ planCodeText(b.code) }}: {{ b.message }} Oprava: {{ b.fix ?? fixes[b.code] ?? 'Oprav příčinu a znovu načti plán.' }}</p>
      <button v-if="active !== 'diff'" data-test="item-apply" :disabled="busy || !plan || !reviewed || !!blockers.length" @click="confirm = true">Provést</button>
    </section>
    <ConfirmDialog :open="confirm" title="Provést zkontrolovaný plán?" :message="`${reviewed?.body.action} · ${reviewed?.repo} · ${reviewed?.body.target}`" confirm-label="Provést" :confirm-disabled="busy || !plan || !!blockers.length" @cancel="confirm = false" @confirm="apply" />
  </section>
</template>
<style scoped>
.items { margin: 24px 0; } .toolbar, .row-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; } .table { overflow-x: auto; } table { width: 100%; border-collapse: collapse; } th, td { padding: 8px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; } th { color: var(--dim); } button, input, select { font: inherit; color: var(--text); background: var(--panel-2); border: 1px solid var(--border); border-radius: 5px; padding: 5px; } button { cursor: pointer; } button:disabled { opacity: .5; cursor: default; } input { max-width: 160px; } label { display: flex; gap: 8px; align-items: center; margin: 8px 0; } fieldset { border: 0; padding: 0; } .operation { margin-top: 16px; padding: 16px; border: 1px solid var(--border); } [role=alert] { color: var(--red); }
</style>
