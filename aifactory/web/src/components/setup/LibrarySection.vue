<script setup lang="ts">
// The library section of #/setup (page Knihovna, #/setup/library): the library lives in $HAIFA_HOME
// of this computer. Without a library it sets one up (from the seed or a clone of the team library).
// On top, the library findings of the machine check. Items of the library by type on the left, the selected item on the right
// with the registered repos that override it with their own copy ("Diff", "move the repo copy
// to the library" through the repo's move plan, and "delete the repo copy" through its remove plan,
// after a confirmation, so the repo inherits the library item again). Import takes a folder from
// the path field or the folder browser of the Add repository page. Re-seed takes the package defaults into the
// library (an item the team changed only when ticked, after its diff). The sync panel shows the
// state against the library remote (local changes, waiting in a PR, in sync) with the open pull
// requests the operator sent, pull and "send as a PR", or connects an empty remote. Changes never
// go to the library branch directly; the library maintainer merges the PRs. Every write emits
// `changed`, so the page checks the machine again.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { FolderOpen } from 'lucide-vue-next'
import { ApiError, applyMove, applyRemove, fetchDirs, previewMove, previewRemove, type CheckFinding, type FactoryFile, type FactoryItemType,
  type FactoryMovePlan, type FactoryRemovePlan } from '@/lib/api'
import { ITEM_TABS, fetchLibrary, fetchItem, fetchOverrides, previewLibrary, applyLibrary, syncLibrary, connectRemote,
  syncState, pullRequestText, versionLabel, type LibraryStatus, type LibraryItem, type ItemDetail, type LibraryPlan, type LibraryRequest,
  type LibraryOverride, type LibraryOverrides, type LibraryPullRequest, type SeedPlanItem } from '@/lib/library'
import { planCodeText } from '@/lib/factory'
import { errorText, shortSha } from '@/lib/format'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import PlanView from '@/components/factory/PlanView.vue'
import FolderBrowser from '@/components/repos/FolderBrowser.vue'
import PathField from '@/components/repos/PathField.vue'
import MachineFinding from './MachineFinding.vue'
import RepoLibraryItems from './RepoLibraryItems.vue'

defineProps<{ findings: CheckFinding[] }>()
const emit = defineEmits<{ changed: [] }>()
const tab = ref<FactoryItemType>('agent')
const library = ref<LibraryStatus | null>(null)
const detail = ref<ItemDetail | null>(null)
const currentItem = ref<LibraryItem | null>(null)
const busy = ref(false)
const loadingDetail = ref(false)
const error = ref('')
const importing = ref(false)
const path = ref('~/')
/** The home folder for the path suggestions, read when the import dialog first opens. */
const home = ref<string | null>(null)
const browsing = ref(false)
const importType = ref<FactoryItemType>('skill')
const plan = ref<LibraryPlan | null>(null)
const importRequest = ref<LibraryRequest | null>(null)
const importResult = ref('')
const overrides = ref<LibraryOverrides | null>(null)
const overrideError = ref('')
const diffFor = ref<LibraryOverride | null>(null)
const movePlan = ref<FactoryMovePlan | null>(null)
const moveConfirm = ref(false)
const removeFor = ref<LibraryOverride | null>(null)
const removePlan = ref<FactoryRemovePlan | null>(null)
const seedPlan = ref<LibraryPlan | null>(null)
const take = ref<string[]>([])
/** The diffs of the items the team changed, from the first seed plan (a taken item has none). */
const keptDiffs = ref<Record<string, FactoryFile[]>>({})
const remoteUrl = ref('')
let generation = 0
const items = computed(() => library.value?.items?.filter(i => i.type === tab.value) ?? [])
/** An older revision is open: repos inherit the current one. */
const oldVersion = computed(() => !!detail.value && !!currentItem.value && detail.value.version !== currentItem.value.version)
const sync = computed(() => library.value ? syncState(library.value) : null)
function overridesOf(type: FactoryItemType, name: string): LibraryOverride[] {
  return overrides.value?.overrides.filter(o => o.type === type && o.name === name) ?? []
}
const itemOverrides = computed(() => currentItem.value ? overridesOf(currentItem.value.type, currentItem.value.name) : [])
const seedItems = computed(() => (seedPlan.value?.items ?? []) as SeedPlanItem[])
const keptItems = computed(() => seedItems.value.filter(i => i.action === 'kept' || i.action === 'take'))
const seedChanges = computed(() => seedItems.value.filter(i => i.action !== 'unchanged' && i.action !== 'kept'))
function key(i: { type: string; name: string }) { return `${i.type}/${i.name}` }
function apiText(e: unknown) { return e instanceof ApiError ? `${planCodeText(e.code)}: ${e.message}` : errorText(e) }
async function loadOverrides() {
  overrideError.value = ''
  try { overrides.value = await fetchOverrides() }
  catch (e) { overrideError.value = errorText(e) }
}
async function load(fresh = false) {
  busy.value = true
  try {
    library.value = await fetchLibrary(fresh)
    if (!library.value.exists && !url.value) url.value = library.value.default_url ?? ''
  }
  catch (e) { error.value = apiText(e) }
  finally { busy.value = false }
  void loadOverrides()
}
async function open(item: LibraryItem, version?: string) {
  const mine = ++generation
  if (currentItem.value?.name !== item.name || currentItem.value?.type !== item.type) { detail.value = null; closeDiff() }
  loadingDetail.value = true; error.value = ''; currentItem.value = item
  try { const value = await fetchItem(item.type, item.name, version); if (mine === generation) detail.value = value }
  catch (e) { if (mine === generation) error.value = errorText(e) }
  finally { if (mine === generation) loadingDetail.value = false }
}
function close() { generation++; detail.value = null; currentItem.value = null; loadingDetail.value = false; closeDiff() }
function changeTab(type: FactoryItemType) { tab.value = type; close() }
async function startImport() {
  importing.value = true
  if (home.value === null) {
    try { home.value = (await fetchDirs()).path }
    catch { /* the field works without suggestions */ }
  }
}
function chooseFolder(folder: string) { path.value = folder; browsing.value = false }
async function planImport() {
  if (busy.value || !path.value.trim()) return
  busy.value = true; error.value = ''; importResult.value = ''
  const request: LibraryRequest = { action: 'import', options: { path: path.value, type: importType.value } }
  try { plan.value = await previewLibrary(request); importRequest.value = request; importing.value = false }
  catch (e) { error.value = errorText(e) }
  finally { busy.value = false }
}
async function performImport() {
  if (busy.value || !plan.value || !importRequest.value || plan.value.blockers.length) return
  busy.value = true; error.value = ''
  try {
    const result = await applyLibrary(importRequest.value, plan.value.digest)
    importResult.value = 'Import dokončen · commit ' + (result.commit ?? 'beze změny') + sentText(result.pull_request)
    tab.value = importRequest.value.options.type ?? tab.value
    close()
    plan.value = null; importRequest.value = null
  } catch (e) { error.value = errorText(e); plan.value = null; importRequest.value = null }
  finally { busy.value = false }
  await load()
  emit('changed')
}
// ── repo copies: diff and move to the library ────────────────────────────────
function closeDiff() { diffFor.value = null; movePlan.value = null; moveConfirm.value = false; removeFor.value = null; removePlan.value = null }
async function showDiff(o: LibraryOverride, confirm = false) {
  if (busy.value) return
  closeDiff(); diffFor.value = o; busy.value = true; error.value = ''; importResult.value = ''
  try { movePlan.value = await previewMove({ type: o.type, name: o.name }, o.repo); moveConfirm.value = confirm }
  catch (e) { error.value = apiText(e); diffFor.value = null }
  finally { busy.value = false }
}
async function performMove() {
  const o = diffFor.value
  if (!o || !movePlan.value || movePlan.value.blockers.length || busy.value) return
  moveConfirm.value = false; busy.value = true; error.value = ''
  try {
    const done = await applyMove({ type: o.type, name: o.name }, movePlan.value.digest, o.repo)
    importResult.value = `${o.type}/${o.name} z repa ${o.repo_name} je v knihovně${done.library_commit ? ` (${shortSha(done.library_commit)})` : ''}.${done.library_commit && library.value?.remote ? ' Na remote odešla jako pull request.' : ''}`
    closeDiff()
  } catch (e) { error.value = apiText(e) }
  finally { busy.value = false }
  await load()
  emit('changed')
  if (currentItem.value) {
    const fresh = library.value?.items?.find(i => i.type === currentItem.value?.type && i.name === currentItem.value?.name)
    if (fresh) await open(fresh)
  }
}
// ── repo copies: delete, so the repo inherits the library item ─────────────────
async function startRemove(o: LibraryOverride) {
  if (busy.value) return
  closeDiff(); busy.value = true; error.value = ''; importResult.value = ''
  try { removePlan.value = await previewRemove({ type: o.type, name: o.name }, o.repo); removeFor.value = o }
  catch (e) { error.value = apiText(e) }
  finally { busy.value = false }
}
function cancelRemove() { if (!busy.value) { removeFor.value = null; removePlan.value = null } }
async function performRemove() {
  const o = removeFor.value
  if (!o || !removePlan.value || removePlan.value.blockers?.length || busy.value) return
  busy.value = true; error.value = ''
  try {
    const done = await applyRemove({ type: o.type, name: o.name }, removePlan.value.digest, o.repo)
    importResult.value = `${o.type}/${o.name}: kopie v repu ${o.repo_name} smazána${done.commit ? ` (${shortSha(done.commit)})` : ''}, repo dědí z knihovny.`
  } catch (e) { error.value = apiText(e) }
  finally { removeFor.value = null; removePlan.value = null; busy.value = false }
  await loadOverrides()
  emit('changed')
}
// ── re-seed ───────────────────────────────────────────────────────────────────
function seedRequest(): LibraryRequest { return { action: 'seed', options: take.value.length ? { take: [...take.value] } : {} } }
async function planSeed() {
  if (busy.value) return
  busy.value = true; error.value = ''; importResult.value = ''
  try {
    seedPlan.value = await previewLibrary(seedRequest())
    for (const i of seedPlan.value.items as SeedPlanItem[]) if (i.diff) keptDiffs.value[key(i)] = i.diff
  }
  catch (e) { error.value = apiText(e) }
  finally { busy.value = false }
}
async function startSeed() { take.value = []; keptDiffs.value = {}; await planSeed() }
async function toggleTake(item: SeedPlanItem, on: boolean) {
  const k = key(item)
  take.value = on ? [...new Set([...take.value, k])] : take.value.filter(t => t !== k)
  await planSeed()
}
async function performSeed() {
  if (busy.value || !seedPlan.value || seedPlan.value.blockers.length) return
  busy.value = true; error.value = ''
  try {
    const result = await applyLibrary(seedRequest(), seedPlan.value.digest)
    importResult.value = 'Výchozí agenti a workflows obnoveny · ' + (result.commit ? 'commit ' + shortSha(result.commit) : 'beze změny') + sentText(result.pull_request)
    seedPlan.value = null; take.value = []
  } catch (e) { error.value = apiText(e); seedPlan.value = null }
  finally { busy.value = false }
  await load()
  emit('changed')
}
// ── sync with the remote ─────────────────────────────────────────────────────
const SYNC_TEXT = { pull: 'Stažení z remote', push: 'Odeslání pull requestu' } as const
/** " · odesláno jako PR #7" after a write that went to the remote as a pull request. */
function sentText(pr: LibraryPullRequest | null | undefined): string { return pr ? ` · odesláno ke schválení: ${pullRequestText(pr)}` : '' }
async function syncWith(action: 'pull' | 'push') {
  if (busy.value) return
  busy.value = true; error.value = ''; importResult.value = ''
  try {
    const data = await syncLibrary(action)
    importResult.value = action === 'push' && !data.pull_request
      ? 'Není co odeslat · všechny lokální změny čekají v pull requestu'
      : `${SYNC_TEXT[action]} dokončeno${sentText(data.pull_request)}`
  }
  catch (e) { error.value = apiText(e) }
  finally { busy.value = false }
  await load()
  emit('changed')
}
async function connect() {
  if (busy.value || !remoteUrl.value.trim()) return
  busy.value = true; error.value = ''; importResult.value = ''
  try { await connectRemote(remoteUrl.value.trim()); importResult.value = 'Knihovna je propojená s remote'; remoteUrl.value = '' }
  catch (e) { error.value = apiText(e) }
  finally { busy.value = false }
  await load()
  emit('changed')
}
// ── set up: from the seed or a clone of the team library ─────────────────────
const url = ref('')
const setupPlan = ref<LibraryPlan | null>(null)
const setupRequest = ref<LibraryRequest | null>(null)
async function previewSetup(action: 'init' | 'clone') {
  if (busy.value) return
  busy.value = true; error.value = ''; importResult.value = ''
  const body: LibraryRequest = { action, options: action === 'clone' ? { url: url.value } : {} }
  try { setupPlan.value = await previewLibrary(body); setupRequest.value = body }
  catch (e) { error.value = apiText(e) }
  finally { busy.value = false }
}
async function performSetup() {
  if (busy.value || !setupPlan.value || !setupRequest.value || setupPlan.value.blockers.length) return
  busy.value = true; error.value = ''
  try {
    const data = await applyLibrary(setupRequest.value, setupPlan.value.digest)
    importResult.value = `Knihovna připravena${data.commit ? ' · commit ' + data.commit : ''}`
  } catch (e) { error.value = apiText(e) }
  finally { setupPlan.value = null; setupRequest.value = null; busy.value = false }
  await load()
  emit('changed')
}
onMounted(() => { void load() })
onBeforeUnmount(() => { generation++ })
</script>
<template>
  <section id="library" class="library-section" data-test="library">
    <header><h2>Obsah knihovny</h2><div class="header-actions">
      <button :disabled="busy || !library?.exists" data-test="library-reseed" @click="startSeed">Obnovit výchozí agenty a workflows</button>
      <button :disabled="busy || !library?.exists" data-test="library-import" @click="startImport">Import…</button>
    </div></header>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="importResult" role="status">{{ importResult }}</p>
    <p v-if="busy || loadingDetail">Načítám…</p>
    <MachineFinding v-for="(f, index) in findings" :key="f.code + index" :finding="f" />
    <form v-if="library && !library.exists" class="actions" data-test="library-setup" @submit.prevent="previewSetup('clone')">
      <p>Knihovna není nastavená. Repa dědí výchozí agenty a workflows z balíčku.</p>
      <label>URL týmové knihovny <input v-model="url" data-test="library-url" :placeholder="library.default_url ?? 'https://…/library.git'" :disabled="busy" /></label>
      <button type="submit" :disabled="busy || !url.trim()" data-test="library-clone">Naklonovat týmovou knihovnu…</button>
      <button type="button" :disabled="busy" data-test="library-init" @click="previewSetup('init')">Založit ze semínka</button>
    </form>
    <section v-if="library?.exists && sync" class="sync" data-test="library-sync">
      <h2>Synchronizace</h2>
      <p class="sync-state" :data-tone="sync.tone" data-test="library-sync-state">{{ sync.text }}</p>
      <dl>
        <dt>Složka</dt><dd class="mono" data-test="library-path">{{ library.library }}</dd>
        <dt>Remote</dt><dd class="mono" data-test="library-remote">{{ library.remote ?? '—' }}</dd>
        <template v-if="library.remote">
          <dt>Větev</dt><dd>{{ library.branch ?? '—' }}</dd>
          <dt>Napřed / pozadu</dt><dd>{{ library.ahead ?? '—' }} / {{ library.behind ?? '—' }}</dd>
          <dt>Poslední fetch</dt><dd>{{ library.last_fetch ?? 'nikdy' }}</dd>
          <dt>Neodeslané commity</dt><dd>{{ library.unsent ?? '—' }}</dd>
        </template>
        <dt>Commit</dt><dd class="mono">{{ library.head ? shortSha(library.head) : '—' }}</dd>
      </dl>
      <p v-if="library.seed_update_available" class="warning" data-test="library-seed-update">
        Balíček má nové výchozí verze: {{ library.seed_updates?.join(', ') }}. Použij „Obnovit výchozí agenty a workflows“.
      </p>
      <template v-if="library.remote">
        <h3>Otevřené pull requesty</h3>
        <ul v-if="library.pull_requests?.length" data-test="library-prs">
          <li v-for="pr in library.pull_requests" :key="pr.branch" data-test="library-pr">
            <a v-if="pr.url" :href="pr.url" target="_blank" rel="noopener">{{ pullRequestText(pr) }}</a>
            <span v-else class="mono">{{ pullRequestText(pr) }}</span>
            · {{ pr.title }}
          </li>
        </ul>
        <p v-else data-test="library-no-prs">Žádné otevřené pull requesty z této knihovny.</p>
        <p v-if="library.pull_requests_error" class="warning">Stav pull requestů se nepodařilo ověřit: {{ library.pull_requests_error }}</p>
        <p class="hint">Změny knihovny jdou na remote jen jako pull request; mergne je správce knihovny. Lokálně platí hned, po mergi stáhni změny.</p>
      </template>
      <div v-if="library.remote" class="actions">
        <button :disabled="busy" data-test="library-fetch" @click="load(true)">Zkontrolovat remote</button>
        <button :disabled="busy || !!library.dirty" data-test="library-pull" @click="syncWith('pull')">Stáhnout</button>
        <button :disabled="busy || !!library.dirty || !library.unsent" data-test="library-push" @click="syncWith('push')">Odeslat jako PR</button>
      </div>
      <form v-else class="actions" @submit.prevent="connect">
        <label>Prázdné git repo <input v-model="remoteUrl" data-test="library-remote-url" :disabled="busy" placeholder="git@github.com:tym/haifa-knihovna.git" /></label>
        <button type="submit" :disabled="busy || !remoteUrl.trim()" data-test="library-connect">Propojit a odeslat</button>
      </form>
    </section>
    <div role="tablist" aria-label="Typ položek" class="item-tabs">
      <button v-for="t in ITEM_TABS" :key="t.type" role="tab" :aria-selected="tab === t.type" :disabled="busy" :data-test="'tab-' + t.type" @click="changeTab(t.type)">{{ t.label }}</button>
    </div>
    <RepoLibraryItems @changed="loadOverrides" :type="tab" :shared="library?.items ?? []" @move="o => { close(); showDiff({ ...o, same: null }, true) }" @import="(p, t) => { path = p; importType = t; planImport() }" />
    <section v-if="diffFor && movePlan && !currentItem" data-test="repo-move-plan">
      <PlanView :plan="movePlan.library_plan" collapsed />
      <PlanView :plan="movePlan" collapsed />
      <button :disabled="busy || !!movePlan.blockers.length" @click="moveConfirm = true">Přesunout do knihovny</button>
    </section>
    <template v-if="library?.exists">
    <h3>Sdílená knihovna</h3>
    <div class="split">
      <div class="list">
        <ul data-test="library-items" class="item-list">
          <li v-for="item in items" :key="item.name" data-test="library-item" :aria-current="currentItem?.name === item.name && currentItem?.type === item.type">
            <button class="item-row" :disabled="busy" @click="open(item)">
              <span class="item-head">
                <strong class="item-name mono">{{ item.name }}</strong>
                <Tooltip :text="overridesOf(item.type, item.name).length ? 'Repa s vlastní kopií' : 'Žádné repo nemá vlastní kopii'"><span class="item-copies" :class="{ none: !overridesOf(item.type, item.name).length }" :data-test="'override-count-' + item.name">{{ overridesOf(item.type, item.name).length || '—' }}</span></Tooltip>
              </span>
              <span class="item-purpose">{{ item.purpose || item.description || '—' }}</span>
              <small class="item-meta">{{ versionLabel(item) }} · {{ item.date }} · {{ item.author }}</small>
            </button>
          </li>
        </ul><p v-if="library?.exists && !items.length" class="hint">Žádné položky tohoto typu</p>
      </div>
      <div class="pane">
        <p v-if="!currentItem" class="hint">Vyber položku vlevo.</p>
        <section v-else-if="detail" data-test="library-detail">
          <button :disabled="busy" @click="close">Zavřít</button>
          <h2>{{ detail.name }} · {{ versionLabel({ ...detail, n: detail.history.find(h => h.version === detail?.version)?.n }) }}</h2>
          <p>{{ detail.purpose || detail.description }}</p>
          <h3>Repa s vlastní kopií</h3>
          <p class="hint">Repa bez vlastní kopie dědí aktuální verzi knihovny.</p>
          <p v-if="overrideError" role="alert">{{ overrideError }}</p>
          <ul v-if="itemOverrides.length" class="override-list" data-test="item-overrides">
            <li v-for="o in itemOverrides" :key="o.repo" class="override-row" :data-test="'override-' + o.repo">
              <strong>{{ o.repo_name }}</strong>
              <small v-if="o.same === true">· shodná s knihovnou</small><small v-else-if="o.same === false">· liší se</small>
              <span class="override-actions"><button :disabled="busy" data-test="override-diff" @click="showDiff(o)">Diff</button>
              <button :disabled="busy" data-test="override-move" @click="showDiff(o, true)">Přesunout kopii repa do knihovny</button>
              <button :disabled="busy" data-test="override-remove" @click="startRemove(o)">Smazat kopii z repa</button></span>
            </li>
          </ul>
          <p v-else class="hint" data-test="item-no-overrides">Žádné registrované repo ji nepřepisuje.</p>
          <p v-for="e in overrides?.errors ?? []" :key="e.repo" class="warning">{{ e.repo_name }}: {{ e.message }}</p>
          <section v-if="diffFor && movePlan" data-test="override-plan">
            <h3>{{ diffFor.repo_name }} → knihovna</h3>
            <PlanView :plan="movePlan.library_plan" collapsed data-test="override-library-plan"><h4>Změna knihovny<template v-if="movePlan.library"> · {{ shortSha(movePlan.library) }}</template></h4></PlanView>
            <PlanView :plan="movePlan" collapsed><h4>Repo · commit do {{ movePlan.base }}</h4></PlanView>
            <button :disabled="busy || !!movePlan.blockers.length" data-test="override-move-apply" @click="moveConfirm = true">Přesunout kopii repa do knihovny</button>
            <button :disabled="busy" @click="closeDiff">Zavřít diff</button>
          </section>
          <h3>Soubory · jen čtení</h3>
          <details v-for="file in detail.files" :key="file.path" data-test="item-file"><summary>{{ file.path }}</summary><pre>{{ file.binary ? 'Binární soubor' : file.content }}</pre></details>
          <h3>Historie verzí</h3>
          <ul data-test="item-history"><li v-for="rev in detail.history" :key="rev.version"><button :disabled="busy || loadingDetail" @click="open(currentItem!, rev.version)">{{ versionLabel(rev) }}</button> · {{ rev.date }} · {{ rev.author }}</li></ul>
          <p v-if="oldVersion" class="warning" data-test="item-old-version">Prohlížíš starší verzi. <button :disabled="busy || loadingDetail" @click="open(currentItem!)">Zobrazit aktuální verzi</button></p>
        </section>
      </div>
    </div>
    </template>
    <ConfirmDialog :open="!!setupPlan" :title="setupRequest?.action === 'clone' ? 'Naklonovat týmovou knihovnu' : 'Založit knihovnu ze semínka'" confirm-label="Potvrdit plán" :confirm-disabled="busy || !!setupPlan?.blockers.length" @confirm="performSetup" @cancel="!busy && (setupPlan = null)">
      <PlanView v-if="setupPlan" :plan="setupPlan" collapsed data-test="library-plan">
        <p v-if="setupPlan.library">{{ typeof setupPlan.library === 'string' ? setupPlan.library : setupPlan.library.name }}</p>
      </PlanView>
    </ConfirmDialog>
    <ConfirmDialog :open="importing && !browsing" title="Import do knihovny" confirm-label="Náhled plánu" :confirm-disabled="busy || !path.trim()" @confirm="planImport" @cancel="!busy && (importing = false)">
      <div class="import-form">
        <p v-if="error" role="alert" class="import-error">{{ error }}</p>
        <div class="field">
          <span class="field-label">Složka</span>
          <div class="folder-row">
            <PathField v-model="path" :home="home" label="Složka pro import" data-test="import-path" :disabled="busy" @submit="planImport" />
            <button type="button" class="browse" :disabled="busy" data-test="import-browse" @click="browsing = true">
              <FolderOpen :size="14" aria-hidden="true" /> Procházet…
            </button>
          </div>
          <span class="field-hint">Složka musí být pod domovskou složkou uživatele.</span>
        </div>
        <label class="field">
          <span class="field-label">Typ</span>
          <SelectMenu v-model="importType" label="Typ importované položky" data-test="import-type" :disabled="busy" :options="ITEM_TABS.map(t => ({ value: t.type, label: t.label }))" />
        </label>
      </div>
    </ConfirmDialog>
    <FolderBrowser :open="importing && browsing" @choose="chooseFolder" @close="browsing = false" />
    <ConfirmDialog :open="!!plan" title="Plán importu" confirm-label="Potvrdit import" :confirm-disabled="busy || !!plan?.blockers.length" @confirm="performImport" @cancel="!busy && (plan = null)"><PlanView v-if="plan" :plan="plan" collapsed data-test="library-plan"><p v-if="plan.library">{{ typeof plan.library === 'string' ? plan.library : plan.library.name }}</p></PlanView></ConfirmDialog>
    <ConfirmDialog :open="!!seedPlan" title="Obnovit výchozí agenty a workflows" :tone="take.length ? 'danger' : 'default'"
      :confirm-label="take.length ? 'Přepsat a obnovit' : 'Obnovit'" :hide-confirm="!seedPlan?.files.length" :cancel-label="seedPlan?.files.length ? 'Zrušit' : 'Zavřít'"
      :confirm-disabled="busy || !!seedPlan?.blockers.length" @confirm="performSeed" @cancel="!busy && (seedPlan = null)">
      <div v-if="seedPlan" data-test="seed-plan">
        <p>Vezme do knihovny výchozí verze z balíčku. Položky, které tým nezměnil, se aktualizují.</p>
        <p v-if="!seedPlan.files.length" data-test="seed-nothing">Knihovna už má všechny výchozí verze.</p>
        <ul v-if="seedChanges.length"><li v-for="i in seedChanges" :key="key(i)">{{ key(i) }} · {{ planCodeText(i.action) }}</li></ul>
        <template v-if="keptItems.length">
          <h3>Změněno týmem</h3>
          <p>Tyto položky tým změnil. Přepíšou se výchozí verzí jen, když je zaškrtneš.</p>
          <div v-for="i in keptItems" :key="key(i)" :data-test="'seed-kept-' + key(i)">
            <label><input type="checkbox" :checked="take.includes(key(i))" :disabled="busy" :data-test="'seed-take-' + key(i)" @change="toggleTake(i, ($event.target as HTMLInputElement).checked)" /> Přepsat {{ key(i) }} výchozí verzí</label>
            <PlanView v-if="keptDiffs[key(i)]?.length" :plan="{ files: keptDiffs[key(i)] }" collapsed />
          </div>
        </template>
        <PlanView :plan="{ blockers: seedPlan.blockers, warnings: seedPlan.warnings }" />
      </div>
    </ConfirmDialog>
    <ConfirmDialog :open="moveConfirm && !!movePlan" :title="`Přesunout ${diffFor?.type}/${diffFor?.name} do knihovny?`"
      message="Zapíše kopii repa do knihovny, smaže ji z repa a commitne obojí. Ostatní repa pak zdědí tuto verzi." confirm-label="Přesunout"
      :confirm-disabled="busy || !movePlan || !!movePlan.blockers.length" @cancel="moveConfirm = false" @confirm="performMove" />
    <ConfirmDialog :open="!!removeFor && !!removePlan" tone="danger" :title="`Smazat ${removeFor?.type}/${removeFor?.name} z repa ${removeFor?.repo_name}?`"
      message="Smaže vlastní kopii z repa a commitne to do base. Repo pak zdědí verzi z knihovny." confirm-label="Smazat kopii"
      :confirm-disabled="busy || !removePlan || !!removePlan.blockers?.length" @cancel="cancelRemove" @confirm="performRemove">
      <PlanView v-if="removePlan" :plan="removePlan" collapsed data-test="override-remove-plan"><h4>Repo · commit do {{ removePlan.base }}</h4></PlanView>
    </ConfirmDialog>
  </section>
</template>
<style scoped>
.library-section > header h2 { margin: 0; }
.item-tabs { display: flex; flex-wrap: wrap; gap: 2px; margin: 16px 0 12px; border-bottom: 1px solid var(--border-soft); }
.item-tabs [role=tab] { margin: 0 0 -1px; border: 0; border-bottom: 2px solid transparent; border-radius: 0; background: none; color: var(--dim); }
.item-tabs [role=tab]:hover { color: var(--text); }
.item-tabs [role=tab][aria-selected=true] { color: var(--text); font-weight: 600; border-bottom-color: var(--cyan); }
.item-list { margin: 0; padding: 0; list-style: none; border: 1px solid var(--border-soft); border-radius: 8px; overflow: hidden; }
.item-list li { border-bottom: 1px solid var(--border-soft); border-left: 3px solid transparent; }
.item-list li:last-child { border-bottom: 0; }
.item-list li[aria-current=true] { border-left-color: var(--cyan); background: var(--panel-2); }
.item-list .item-row { display: flex; flex-direction: column; gap: 3px; width: 100%; margin: 0; padding: 10px 12px; border: 0; border-radius: 0; background: none; text-align: left; color: var(--text); }
.item-list .item-row:hover:not(:disabled) { background: var(--panel-2); }
.item-list .item-row:disabled { opacity: 1; }
.item-list .item-row:focus-visible { outline: 2px solid var(--cyan); outline-offset: -2px; }
.item-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }
.item-name { font-weight: 700; }
.item-copies { flex: none; min-width: 22px; padding: 0 7px; border: 1px solid var(--border); border-radius: 999px; font-size: 12px; text-align: center; color: var(--amber); }
.item-copies.none { border-color: transparent; color: var(--faint); }
.item-purpose { color: var(--dim); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.item-meta { color: var(--faint); font-size: 12px; }
.library-section ul.override-list { padding-left: 0; list-style: none; }
.override-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 6px 0; }
.override-row .override-actions { display: flex; flex-wrap: wrap; gap: 6px; width: 100%; }
.override-row .override-actions button { margin: 0; }
.import-form { display: flex; flex-direction: column; gap: 14px; }
.import-error { margin: 0; color: var(--red); }
.field { display: flex; flex-direction: column; gap: 6px; }
.field-label { font-weight: 600; }
.field-hint { color: var(--dim); font-size: 13px; }
.folder-row { display: flex; align-items: flex-start; gap: 8px; }
.browse { display: inline-flex; flex: none; align-items: center; gap: 6px; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2); color: var(--text); font: inherit; white-space: nowrap; cursor: pointer; }
.browse:disabled { opacity: .5; cursor: default; }
</style>
