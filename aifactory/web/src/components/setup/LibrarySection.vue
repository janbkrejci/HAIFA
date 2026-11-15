<script setup lang="ts">
import { t } from '@/lib/i18n'
import { setupErrorText } from '@/lib/setupMessages'
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
import { applyMove, applyRemove, fetchDirs, previewMove, previewRemove, type CheckFinding, type FactoryFile, type FactoryItemType,
  type FactoryMovePlan, type FactoryRemovePlan } from '@/lib/api'
import { ITEM_TABS, fetchLibrary, fetchItem, fetchOverrides, previewLibrary, applyLibrary, syncLibrary, connectRemote,
  syncState, pullRequestText, versionLabel, type LibraryStatus, type LibraryItem, type ItemDetail, type LibraryPlan, type LibraryRequest,
  type LibraryOverride, type LibraryOverrides, type LibraryPullRequest, type SeedPlanItem } from '@/lib/library'
import { planCodeText } from '@/lib/factory'
import { shortSha } from '@/lib/format'
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
const error = ref<unknown>(null)
const importing = ref(false)
const path = ref('~/')
/** The home folder for the path suggestions, read when the import dialog first opens. */
const home = ref<string | null>(null)
const browsing = ref(false)
const importType = ref<FactoryItemType>('skill')
const plan = ref<LibraryPlan | null>(null)
const importRequest = ref<LibraryRequest | null>(null)
const importResult = ref<(() => string) | null>(null)
const overrides = ref<LibraryOverrides | null>(null)
const overrideError = ref<unknown>(null)
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
async function loadOverrides() {
  overrideError.value = null
  try { overrides.value = await fetchOverrides() }
  catch (e) { overrideError.value = e }
}
async function load(fresh = false) {
  busy.value = true
  try {
    library.value = await fetchLibrary(fresh)
    if (!library.value.exists && !url.value) url.value = library.value.default_url ?? ''
  }
  catch (e) { error.value = e }
  finally { busy.value = false }
  void loadOverrides()
}
async function open(item: LibraryItem, version?: string) {
  const mine = ++generation
  if (currentItem.value?.name !== item.name || currentItem.value?.type !== item.type) { detail.value = null; closeDiff() }
  loadingDetail.value = true; error.value = null; currentItem.value = item
  try { const value = await fetchItem(item.type, item.name, version); if (mine === generation) detail.value = value }
  catch (e) { if (mine === generation) error.value = e }
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
  busy.value = true; error.value = null; importResult.value = null
  const request: LibraryRequest = { action: 'import', options: { path: path.value, type: importType.value } }
  try { plan.value = await previewLibrary(request); importRequest.value = request; importing.value = false }
  catch (e) { error.value = e }
  finally { busy.value = false }
}
async function performImport() {
  if (busy.value || !plan.value || !importRequest.value || plan.value.blockers.length) return
  busy.value = true; error.value = null
  try {
    const result = await applyLibrary(importRequest.value, plan.value.digest)
    importResult.value = () => t('setup.importDone', { commit: result.commit ?? t('setup.noChange'), sent: sentText(result.pull_request) })
    tab.value = importRequest.value.options.type ?? tab.value
    close()
    plan.value = null; importRequest.value = null
  } catch (e) { error.value = e; plan.value = null; importRequest.value = null }
  finally { busy.value = false }
  await load()
  emit('changed')
}
// ── repo copies: diff and move to the library ────────────────────────────────
function closeDiff() { diffFor.value = null; movePlan.value = null; moveConfirm.value = false; removeFor.value = null; removePlan.value = null }
async function showDiff(o: LibraryOverride, confirm = false) {
  if (busy.value) return
  closeDiff(); diffFor.value = o; busy.value = true; error.value = null; importResult.value = null
  try { movePlan.value = await previewMove({ type: o.type, name: o.name }, o.repo); moveConfirm.value = confirm }
  catch (e) { error.value = e; diffFor.value = null }
  finally { busy.value = false }
}
async function performMove() {
  const o = diffFor.value
  if (!o || !movePlan.value || movePlan.value.blockers.length || busy.value) return
  moveConfirm.value = false; busy.value = true; error.value = null
  try {
    const done = await applyMove({ type: o.type, name: o.name }, movePlan.value.digest, o.repo)
    importResult.value = () => t('setup.moveDone', { item: `${o.type}/${o.name}`, repo: o.repo_name, commit: done.library_commit ? ` (${shortSha(done.library_commit)})` : '', sent: done.library_commit && library.value?.remote ? t('setup.sentRemote') : '' })
    closeDiff()
  } catch (e) { error.value = e }
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
  closeDiff(); busy.value = true; error.value = null; importResult.value = null
  try { removePlan.value = await previewRemove({ type: o.type, name: o.name }, o.repo); removeFor.value = o }
  catch (e) { error.value = e }
  finally { busy.value = false }
}
function cancelRemove() { if (!busy.value) { removeFor.value = null; removePlan.value = null } }
async function performRemove() {
  const o = removeFor.value
  if (!o || !removePlan.value || removePlan.value.blockers?.length || busy.value) return
  busy.value = true; error.value = null
  try {
    const done = await applyRemove({ type: o.type, name: o.name }, removePlan.value.digest, o.repo)
    importResult.value = () => t('setup.removeDone', { item: `${o.type}/${o.name}`, repo: o.repo_name, commit: done.commit ? ` (${shortSha(done.commit)})` : '' })
  } catch (e) { error.value = e }
  finally { removeFor.value = null; removePlan.value = null; busy.value = false }
  await loadOverrides()
  emit('changed')
}
// ── re-seed ───────────────────────────────────────────────────────────────────
function seedRequest(): LibraryRequest { return { action: 'seed', options: take.value.length ? { take: [...take.value] } : {} } }
async function planSeed() {
  if (busy.value) return
  busy.value = true; error.value = null; importResult.value = null
  try {
    seedPlan.value = await previewLibrary(seedRequest())
    for (const i of seedPlan.value.items as SeedPlanItem[]) if (i.diff) keptDiffs.value[key(i)] = i.diff
  }
  catch (e) { error.value = e }
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
  busy.value = true; error.value = null
  try {
    const result = await applyLibrary(seedRequest(), seedPlan.value.digest)
    importResult.value = () => t('setup.seedDone', { commit: result.commit ? 'commit ' + shortSha(result.commit) : t('setup.noChange'), sent: sentText(result.pull_request) })
    seedPlan.value = null; take.value = []
  } catch (e) { error.value = e; seedPlan.value = null }
  finally { busy.value = false }
  await load()
  emit('changed')
}
// ── sync with the remote ─────────────────────────────────────────────────────
const SYNC_TEXT = { pull: 'setup.pullAction', push: 'setup.pushAction' } as const
/** " · odesláno jako PR #7" after a write that went to the remote as a pull request. */
function sentText(pr: LibraryPullRequest | null | undefined): string { return pr ? t('setup.sent', { pr: pullRequestText(pr) }) : '' }
async function syncWith(action: 'pull' | 'push') {
  if (busy.value) return
  busy.value = true; error.value = null; importResult.value = null
  try {
    const data = await syncLibrary(action)
    importResult.value = () => action === 'push' && !data.pull_request
      ? t('setup.nothingToPush')
      : t('setup.syncDone', { action: t(SYNC_TEXT[action]), sent: sentText(data.pull_request) })
  }
  catch (e) { error.value = e }
  finally { busy.value = false }
  await load()
  emit('changed')
}
async function connect() {
  if (busy.value || !remoteUrl.value.trim()) return
  busy.value = true; error.value = null; importResult.value = null
  try { await connectRemote(remoteUrl.value.trim()); importResult.value = () => t('setup.connected'); remoteUrl.value = '' }
  catch (e) { error.value = e }
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
  busy.value = true; error.value = null; importResult.value = null
  const body: LibraryRequest = { action, options: action === 'clone' ? { url: url.value } : {} }
  try { setupPlan.value = await previewLibrary(body); setupRequest.value = body }
  catch (e) { error.value = e }
  finally { busy.value = false }
}
async function performSetup() {
  if (busy.value || !setupPlan.value || !setupRequest.value || setupPlan.value.blockers.length) return
  busy.value = true; error.value = null
  try {
    const data = await applyLibrary(setupRequest.value, setupPlan.value.digest)
    importResult.value = () => t('setup.ready', { commit: data.commit ? ' · commit ' + data.commit : '' })
  } catch (e) { error.value = e }
  finally { setupPlan.value = null; setupRequest.value = null; busy.value = false }
  await load()
  emit('changed')
}
onMounted(() => { void load() })
onBeforeUnmount(() => { generation++ })
</script>
<template>
  <section id="library" class="library-section" data-test="library">
    <header><h2>{{ t('setup.contents') }}</h2><div class="header-actions">
      <button :disabled="busy || !library?.exists" data-test="library-reseed" @click="startSeed">{{ t('setup.restoreDefaults') }}</button>
      <button :disabled="busy || !library?.exists" data-test="library-import" @click="startImport">{{ t('setup.import') }}</button>
    </div></header>
    <p v-if="error" role="alert">{{ setupErrorText(error) }}</p><details v-if="error"><summary>{{ t('dashboard.diagnostics') }}</summary>{{ String(error) }}</details><p v-if="importResult" role="status">{{ importResult() }}</p>
    <p v-if="busy || loadingDetail">{{ t('setup.loading') }}</p>
    <MachineFinding v-for="(f, index) in findings" :key="f.code + index" :finding="f" />
    <form v-if="library && !library.exists" class="actions" data-test="library-setup" @submit.prevent="previewSetup('clone')">
      <p>{{ t('setup.notConfigured') }}</p>
      <label>{{ t('setup.teamUrl') }} <input v-model="url" data-test="library-url" :placeholder="library.default_url ?? 'https://…/library.git'" :disabled="busy" /></label>
      <button type="submit" :disabled="busy || !url.trim()" data-test="library-clone">{{ t('setup.cloneTeam') }}</button>
      <button type="button" :disabled="busy" data-test="library-init" @click="previewSetup('init')">{{ t('setup.initSeed') }}</button>
    </form>
    <section v-if="library?.exists && sync" class="sync" data-test="library-sync">
      <h2>{{ t('setup.sync') }}</h2>
      <p class="sync-state" :data-tone="sync.tone" data-test="library-sync-state">{{ sync.text }}</p>
      <dl>
        <dt>{{ t('setup.folder') }}</dt><dd class="mono" data-test="library-path">{{ library.library }}</dd>
        <dt>Remote</dt><dd class="mono" data-test="library-remote">{{ library.remote ?? '—' }}</dd>
        <template v-if="library.remote">
          <dt>{{ t('setup.branch') }}</dt><dd>{{ library.branch ?? '—' }}</dd>
          <dt>{{ t('setup.aheadBehind') }}</dt><dd>{{ library.ahead ?? '—' }} / {{ library.behind ?? '—' }}</dd>
          <dt>{{ t('setup.lastFetch') }}</dt><dd>{{ library.last_fetch ?? t('setup.never') }}</dd>
          <dt>{{ t('setup.unsent') }}</dt><dd>{{ library.unsent ?? '—' }}</dd>
        </template>
        <dt>Commit</dt><dd class="mono">{{ library.head ? shortSha(library.head) : '—' }}</dd>
      </dl>
      <p v-if="library.seed_update_available" class="warning" data-test="library-seed-update">
        {{ t('setup.seedUpdate', { items: library.seed_updates?.join(', ') ?? '' }) }}
      </p>
      <template v-if="library.remote">
        <h3>{{ t('setup.openPrs') }}</h3>
        <ul v-if="library.pull_requests?.length" data-test="library-prs">
          <li v-for="pr in library.pull_requests" :key="pr.branch" data-test="library-pr">
            <a v-if="pr.url" :href="pr.url" target="_blank" rel="noopener">{{ pullRequestText(pr) }}</a>
            <span v-else class="mono">{{ pullRequestText(pr) }}</span>
            · {{ pr.title }}
          </li>
        </ul>
        <p v-else data-test="library-no-prs">{{ t('setup.noPrs') }}</p>
        <p v-if="library.pull_requests_error" class="warning">{{ t('setup.prError') }} {{ library.pull_requests_error }}</p>
        <p class="hint">{{ t('setup.prHint') }}</p>
      </template>
      <div v-if="library.remote" class="actions">
        <button :disabled="busy" data-test="library-fetch" @click="load(true)">{{ t('setup.checkRemote') }}</button>
        <button :disabled="busy || !!library.dirty" data-test="library-pull" @click="syncWith('pull')">{{ t('setup.pull') }}</button>
        <button :disabled="busy || !!library.dirty || !library.unsent" data-test="library-push" @click="syncWith('push')">{{ t('setup.push') }}</button>
      </div>
      <form v-else class="actions" @submit.prevent="connect">
        <label>{{ t('setup.emptyRepo') }} <input v-model="remoteUrl" data-test="library-remote-url" :disabled="busy" placeholder="git@github.com:tym/haifa-knihovna.git" /></label>
        <button type="submit" :disabled="busy || !remoteUrl.trim()" data-test="library-connect">{{ t('setup.connect') }}</button>
      </form>
    </section>
    <div role="tablist" :aria-label="t('setup.itemTypes')" class="item-tabs">
      <button v-for="itemTab in ITEM_TABS" :key="itemTab.type" role="tab" :aria-selected="tab === itemTab.type" :disabled="busy" :data-test="'tab-' + itemTab.type" @click="changeTab(itemTab.type)">{{ t(itemTab.label) }}</button>
    </div>
    <RepoLibraryItems @changed="loadOverrides" :type="tab" :shared="library?.items ?? []" @move="o => { close(); showDiff({ ...o, same: null }, true) }" @import="(p, t) => { path = p; importType = t; planImport() }" />
    <section v-if="diffFor && movePlan && !currentItem" data-test="repo-move-plan">
      <PlanView :plan="movePlan.library_plan" collapsed />
      <PlanView :plan="movePlan" collapsed />
      <button :disabled="busy || !!movePlan.blockers.length" @click="moveConfirm = true">{{ t('setup.moveLibrary') }}</button>
    </section>
    <template v-if="library?.exists">
    <h3>{{ t('setup.sharedLibrary') }}</h3>
    <div class="split">
      <div class="list">
        <ul data-test="library-items" class="item-list">
          <li v-for="item in items" :key="item.name" data-test="library-item" :aria-current="currentItem?.name === item.name && currentItem?.type === item.type">
            <button class="item-row" :disabled="busy" @click="open(item)">
              <span class="item-head">
                <strong class="item-name mono">{{ item.name }}</strong>
                <Tooltip :text="overridesOf(item.type, item.name).length ? t('setup.repoCopies') : t('setup.noCopies')"><span class="item-copies" :class="{ none: !overridesOf(item.type, item.name).length }" :data-test="'override-count-' + item.name">{{ overridesOf(item.type, item.name).length || '—' }}</span></Tooltip>
              </span>
              <span class="item-purpose">{{ item.purpose || item.description || '—' }}</span>
              <small class="item-meta">{{ versionLabel(item) }} · {{ item.date }} · {{ item.author }}</small>
            </button>
          </li>
        </ul><p v-if="library?.exists && !items.length" class="hint">{{ t('setup.noItems') }}</p>
      </div>
      <div class="pane">
        <p v-if="!currentItem" class="hint">{{ t('setup.selectItem') }}</p>
        <section v-else-if="detail" data-test="library-detail">
          <button :disabled="busy" @click="close">{{ t('setup.close') }}</button>
          <h2>{{ detail.name }} · {{ versionLabel({ ...detail, n: detail.history.find(h => h.version === detail?.version)?.n }) }}</h2>
          <p>{{ detail.purpose || detail.description }}</p>
          <h3>{{ t('setup.repoCopies') }}</h3>
          <p class="hint">{{ t('setup.inheritHint') }}</p>
          <p v-if="overrideError" role="alert">{{ setupErrorText(overrideError) }}</p><details v-if="overrideError"><summary>{{ t('dashboard.diagnostics') }}</summary>{{ String(overrideError) }}</details>
          <ul v-if="itemOverrides.length" class="override-list" data-test="item-overrides">
            <li v-for="o in itemOverrides" :key="o.repo" class="override-row" :data-test="'override-' + o.repo">
              <strong>{{ o.repo_name }}</strong>
              <small v-if="o.same === true">{{ t('setup.same') }}</small><small v-else-if="o.same === false">{{ t('setup.different') }}</small>
              <span class="override-actions"><button :disabled="busy" data-test="override-diff" @click="showDiff(o)">Diff</button>
              <button :disabled="busy" data-test="override-move" @click="showDiff(o, true)">{{ t('setup.moveCopy') }}</button>
              <button :disabled="busy" data-test="override-remove" @click="startRemove(o)">{{ t('setup.removeCopy') }}</button></span>
            </li>
          </ul>
          <p v-else class="hint" data-test="item-no-overrides">{{ t('setup.noOverrides') }}</p>
          <div v-for="e in overrides?.errors ?? []" :key="e.repo" class="warning">{{ t('setup.repoReadError', { repo: e.repo_name }) }}<details><summary>{{ t('dashboard.diagnostics') }}</summary>{{ e.repo_name }}: {{ e.message }}</details></div>
          <section v-if="diffFor && movePlan" data-test="override-plan">
            <h3>{{ diffFor.repo_name }} → {{ t('setup.library') }}</h3>
            <PlanView :plan="movePlan.library_plan" collapsed data-test="override-library-plan"><h4>{{ t('setup.libraryChange') }}<template v-if="movePlan.library"> · {{ shortSha(movePlan.library) }}</template></h4></PlanView>
            <PlanView :plan="movePlan" collapsed><h4>{{ t('setup.repoCommit') }} {{ movePlan.base }}</h4></PlanView>
            <button :disabled="busy || !!movePlan.blockers.length" data-test="override-move-apply" @click="moveConfirm = true">{{ t('setup.moveCopy') }}</button>
            <button :disabled="busy" @click="closeDiff">{{ t('setup.closeDiff') }}</button>
          </section>
          <h3>{{ t('setup.readOnly') }}</h3>
          <details v-for="file in detail.files" :key="file.path" data-test="item-file"><summary>{{ file.path }}</summary><pre>{{ file.binary ? t('setup.binary') : file.content }}</pre></details>
          <h3>{{ t('setup.history') }}</h3>
          <ul data-test="item-history"><li v-for="rev in detail.history" :key="rev.version"><button :disabled="busy || loadingDetail" @click="open(currentItem!, rev.version)">{{ versionLabel(rev) }}</button> · {{ rev.date }} · {{ rev.author }}</li></ul>
          <p v-if="oldVersion" class="warning" data-test="item-old-version">{{ t('setup.oldVersion') }} <button :disabled="busy || loadingDetail" @click="open(currentItem!)">{{ t('setup.currentVersion') }}</button></p>
        </section>
      </div>
    </div>
    </template>
    <ConfirmDialog :open="!!setupPlan" :title="setupRequest?.action === 'clone' ? t('setup.cloneTitle') : t('setup.initTitle')" :confirm-label="t('setup.confirmPlan')" :confirm-disabled="busy || !!setupPlan?.blockers.length" @confirm="performSetup" @cancel="!busy && (setupPlan = null)">
      <PlanView v-if="setupPlan" :plan="setupPlan" collapsed data-test="library-plan">
        <p v-if="setupPlan.library">{{ typeof setupPlan.library === 'string' ? setupPlan.library : setupPlan.library.name }}</p>
      </PlanView>
    </ConfirmDialog>
    <ConfirmDialog :open="importing && !browsing" :title="t('setup.importTitle')" :confirm-label="t('setup.preview')" :confirm-disabled="busy || !path.trim()" @confirm="planImport" @cancel="!busy && (importing = false)">
      <div class="import-form">
        <p v-if="error" role="alert" class="import-error">{{ setupErrorText(error) }}</p><details v-if="error"><summary>{{ t('dashboard.diagnostics') }}</summary>{{ String(error) }}</details>
        <div class="field">
          <span class="field-label">{{ t('setup.folder') }}</span>
          <div class="folder-row">
            <PathField v-model="path" :home="home" :label="t('setup.importFolder')" data-test="import-path" :disabled="busy" @submit="planImport" />
            <button type="button" class="browse" :disabled="busy" data-test="import-browse" @click="browsing = true">
              <FolderOpen :size="14" aria-hidden="true" /> {{ t('setup.browse') }}
            </button>
          </div>
          <span class="field-hint">{{ t('setup.underHome') }}</span>
        </div>
        <label class="field">
          <span class="field-label">{{ t('setup.type') }}</span>
          <SelectMenu v-model="importType" :label="t('setup.importType')" data-test="import-type" :disabled="busy" :options="ITEM_TABS.map(tab => ({ value: tab.type, label: t(tab.label) }))" />
        </label>
      </div>
    </ConfirmDialog>
    <FolderBrowser :open="importing && browsing" @choose="chooseFolder" @close="browsing = false" />
    <ConfirmDialog :open="!!plan" :title="t('setup.importPlan')" :confirm-label="t('setup.confirmImport')" :confirm-disabled="busy || !!plan?.blockers.length" @confirm="performImport" @cancel="!busy && (plan = null)"><PlanView v-if="plan" :plan="plan" collapsed data-test="library-plan"><p v-if="plan.library">{{ typeof plan.library === 'string' ? plan.library : plan.library.name }}</p></PlanView></ConfirmDialog>
    <ConfirmDialog :open="!!seedPlan" :title="t('setup.restoreDefaults')" :tone="take.length ? 'danger' : 'default'"
      :confirm-label="take.length ? t('setup.overwriteRestore') : t('setup.restore')" :hide-confirm="!seedPlan?.files.length" :cancel-label="seedPlan?.files.length ? t('setup.cancel') : t('setup.close')"
      :confirm-disabled="busy || !!seedPlan?.blockers.length" @confirm="performSeed" @cancel="!busy && (seedPlan = null)">
      <div v-if="seedPlan" data-test="seed-plan">
        <p>{{ t('setup.seedHint') }}</p>
        <p v-if="!seedPlan.files.length" data-test="seed-nothing">{{ t('setup.seedNothing') }}</p>
        <ul v-if="seedChanges.length"><li v-for="i in seedChanges" :key="key(i)">{{ key(i) }} · {{ planCodeText(i.action) }}</li></ul>
        <template v-if="keptItems.length">
          <h3>{{ t('setup.teamChanged') }}</h3>
          <p>{{ t('setup.teamChangedHint') }}</p>
          <div v-for="i in keptItems" :key="key(i)" :data-test="'seed-kept-' + key(i)">
            <label><input type="checkbox" :checked="take.includes(key(i))" :disabled="busy" :data-test="'seed-take-' + key(i)" @change="toggleTake(i, ($event.target as HTMLInputElement).checked)" /> {{ t('setup.overwrite', { item: key(i) }) }}</label>
            <PlanView v-if="keptDiffs[key(i)]?.length" :plan="{ files: keptDiffs[key(i)] }" collapsed />
          </div>
        </template>
        <PlanView :plan="{ blockers: seedPlan.blockers, warnings: seedPlan.warnings }" />
      </div>
    </ConfirmDialog>
    <ConfirmDialog :open="moveConfirm && !!movePlan" :title="t('setup.moveTitle', { item: `${diffFor?.type}/${diffFor?.name}` })"
      :message="t('setup.moveMessage')" :confirm-label="t('setup.move')"
      :confirm-disabled="busy || !movePlan || !!movePlan.blockers.length" @cancel="moveConfirm = false" @confirm="performMove" />
    <ConfirmDialog :open="!!removeFor && !!removePlan" tone="danger" :title="t('setup.removeTitle', { item: `${removeFor?.type}/${removeFor?.name}`, repo: removeFor?.repo_name ?? '' })"
      :message="t('setup.removeMessage')" :confirm-label="t('setup.deleteCopy')"
      :confirm-disabled="busy || !removePlan || !!removePlan.blockers?.length" @cancel="cancelRemove" @confirm="performRemove">
      <PlanView v-if="removePlan" :plan="removePlan" collapsed data-test="override-remove-plan"><h4>{{ t('setup.repoCommit') }} {{ removePlan.base }}</h4></PlanView>
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
