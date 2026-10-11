<script setup lang="ts">
// The library screen: items of the library by type on the left, the selected item on the right
// with the registered repos that override it with their own copy ("Diff" and "move the repo copy
// to the library" through the repo's move plan). Re-seed takes the package defaults into the
// library (an item the team changed only when ticked, after its diff). The sync panel shows the
// state against the library remote, with pull and push, or connects an empty remote.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { ApiError, applyMove, previewMove, type FactoryFile, type FactoryItemType, type FactoryMovePlan } from '@/lib/api'
import { ITEM_TABS, fetchLibrary, fetchItem, fetchOverrides, previewLibrary, applyLibrary, syncLibrary, connectRemote,
  syncState, versionLabel, type LibraryStatus, type LibraryItem, type ItemDetail, type LibraryPlan, type LibraryRequest,
  type LibraryOverride, type LibraryOverrides, type SeedPlanItem } from '@/lib/library'
import { planCodeText } from '@/lib/factory'
import { errorText, shortSha } from '@/lib/format'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import PlanView from '@/components/factory/PlanView.vue'
const tab = ref<FactoryItemType>('agent')
const library = ref<LibraryStatus | null>(null)
const detail = ref<ItemDetail | null>(null)
const currentItem = ref<LibraryItem | null>(null)
const busy = ref(false)
const loadingDetail = ref(false)
const error = ref('')
const importing = ref(false)
const path = ref('')
const importType = ref<FactoryItemType>('skill')
const plan = ref<LibraryPlan | null>(null)
const importRequest = ref<LibraryRequest | null>(null)
const importResult = ref('')
const overrides = ref<LibraryOverrides | null>(null)
const overrideError = ref('')
const diffFor = ref<LibraryOverride | null>(null)
const movePlan = ref<FactoryMovePlan | null>(null)
const moveConfirm = ref(false)
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
  try { library.value = await fetchLibrary(fresh) }
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
    importResult.value = 'Import dokončen · commit ' + (result.commit ?? 'beze změny')
    tab.value = importRequest.value.options.type ?? tab.value
    close()
    plan.value = null; importRequest.value = null
  } catch (e) { error.value = errorText(e); plan.value = null; importRequest.value = null }
  finally { busy.value = false }
  await load()
}
// ── repo copies: diff and move to the library ────────────────────────────────
function closeDiff() { diffFor.value = null; movePlan.value = null; moveConfirm.value = false }
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
    importResult.value = `${o.type}/${o.name} z repa ${o.repo_name} je v knihovně${done.library_commit ? ` (${shortSha(done.library_commit)})` : ''}.`
    closeDiff()
  } catch (e) { error.value = apiText(e) }
  finally { busy.value = false }
  await load()
  if (currentItem.value) {
    const fresh = library.value?.items?.find(i => i.type === currentItem.value?.type && i.name === currentItem.value?.name)
    if (fresh) await open(fresh)
  }
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
    importResult.value = 'Výchozí agenti a workflows obnoveny · ' + (result.commit ? 'commit ' + shortSha(result.commit) : 'beze změny')
    seedPlan.value = null; take.value = []
  } catch (e) { error.value = apiText(e); seedPlan.value = null }
  finally { busy.value = false }
  await load()
}
// ── sync with the remote ─────────────────────────────────────────────────────
const SYNC_TEXT = { pull: 'Stažení z remote', push: 'Odeslání na remote' } as const
async function syncWith(action: 'pull' | 'push') {
  if (busy.value) return
  busy.value = true; error.value = ''; importResult.value = ''
  try { await syncLibrary(action); importResult.value = `${SYNC_TEXT[action]} dokončeno` }
  catch (e) { error.value = apiText(e) }
  finally { busy.value = false }
  await load()
}
async function connect() {
  if (busy.value || !remoteUrl.value.trim()) return
  busy.value = true; error.value = ''; importResult.value = ''
  try { await connectRemote(remoteUrl.value.trim()); importResult.value = 'Knihovna je propojená s remote'; remoteUrl.value = '' }
  catch (e) { error.value = apiText(e) }
  finally { busy.value = false }
  await load()
}
onMounted(() => { void load() })
onBeforeUnmount(() => { generation++ })
</script>
<template>
  <section class="global-page" data-test="library">
    <header><h1>Knihovna</h1><div class="header-actions">
      <button :disabled="busy || !library?.exists" data-test="library-reseed" @click="startSeed">Obnovit výchozí agenty a workflows</button>
      <button :disabled="busy || !library?.exists" data-test="library-import" @click="importing = true">Import…</button>
    </div></header>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="importResult" role="status">{{ importResult }}</p>
    <p v-if="busy || loadingDetail">Načítám…</p>
    <p v-if="library && !library.exists">Knihovna není nastavená. Repa dědí výchozí agenty a workflows z balíčku. <a href="#/setup">Nastavit na tomto počítači</a></p>
    <section v-if="library?.exists && sync" class="sync" data-test="library-sync">
      <h2>Synchronizace</h2>
      <p class="sync-state" :data-tone="sync.tone" data-test="library-sync-state">{{ sync.text }}</p>
      <dl>
        <dt>Složka</dt><dd class="mono">{{ library.library }}</dd>
        <dt>Remote</dt><dd class="mono" data-test="library-remote">{{ library.remote ?? '—' }}</dd>
        <template v-if="library.remote">
          <dt>Větev</dt><dd>{{ library.branch ?? '—' }}</dd>
          <dt>Napřed / pozadu</dt><dd>{{ library.ahead ?? '—' }} / {{ library.behind ?? '—' }}</dd>
          <dt>Poslední fetch</dt><dd>{{ library.last_fetch ?? 'nikdy' }}</dd>
        </template>
        <dt>Commit</dt><dd class="mono">{{ library.head ? shortSha(library.head) : '—' }}</dd>
      </dl>
      <p v-if="library.seed_update_available" class="warning" data-test="library-seed-update">
        Balíček má nové výchozí verze: {{ library.seed_updates?.join(', ') }}. Použij „Obnovit výchozí agenty a workflows“.
      </p>
      <div v-if="library.remote" class="actions">
        <button :disabled="busy" data-test="library-fetch" @click="load(true)">Zkontrolovat remote</button>
        <button :disabled="busy || !!library.dirty" data-test="library-pull" @click="syncWith('pull')">Stáhnout</button>
        <button :disabled="busy || !!library.dirty" data-test="library-push" @click="syncWith('push')">Odeslat</button>
      </div>
      <form v-else class="actions" @submit.prevent="connect">
        <label>Prázdné git repo <input v-model="remoteUrl" data-test="library-remote-url" :disabled="busy" placeholder="git@github.com:tym/haifa-knihovna.git" /></label>
        <button type="submit" :disabled="busy || !remoteUrl.trim()" data-test="library-connect">Propojit a odeslat</button>
      </form>
    </section>
    <div role="tablist" aria-label="Typ položek">
      <button v-for="t in ITEM_TABS" :key="t.type" role="tab" :aria-selected="tab === t.type" :disabled="busy" :data-test="'tab-' + t.type" @click="changeTab(t.type)">{{ t.label }}</button>
    </div>
    <div class="split">
      <div class="list">
        <div class="table-scroll"><table data-test="library-items">
          <thead><tr><th>Jméno</th><th>Účel / popis</th><th>Verze</th><th>Kopie v repech</th></tr></thead>
          <tbody><tr v-for="item in items" :key="item.name" data-test="library-item" :aria-current="currentItem?.name === item.name && currentItem?.type === item.type">
            <td><button :disabled="busy" @click="open(item)">{{ item.name }}</button></td><td>{{ item.purpose || item.description || '—' }}</td>
            <td>{{ versionLabel(item) }}<br><small>{{ item.date }} · {{ item.author }}</small></td>
            <td :data-test="'override-count-' + item.name">{{ overridesOf(item.type, item.name).length || '—' }}</td>
          </tr></tbody>
        </table></div><p v-if="library?.exists && !items.length">Žádné položky tohoto typu</p>
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
          <ul v-if="itemOverrides.length" data-test="item-overrides">
            <li v-for="o in itemOverrides" :key="o.repo" :data-test="'override-' + o.repo">
              <strong>{{ o.repo_name }}</strong>
              <small v-if="o.same === true"> · shodná s knihovnou</small><small v-else-if="o.same === false"> · liší se</small>
              <button :disabled="busy" data-test="override-diff" @click="showDiff(o)">Diff</button>
              <button :disabled="busy" data-test="override-move" @click="showDiff(o, true)">Přesunout kopii repa do knihovny</button>
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
    <ConfirmDialog :open="importing" title="Import do knihovny" confirm-label="Náhled plánu" :confirm-disabled="busy || !path.trim()" @confirm="planImport" @cancel="!busy && (importing = false)">
      <p v-if="error" role="alert">{{ error }}</p>
      <p>Složka musí být pod domovskou složkou uživatele.</p>
      <label>Složka <input v-model="path" data-test="import-path" :disabled="busy" placeholder="~/moje-skilly/demo" /></label>
      <label>Typ <SelectMenu v-model="importType" label="Typ importované položky" data-test="import-type" :disabled="busy" :options="ITEM_TABS.map(t => ({ value: t.type, label: t.label }))" /></label>
    </ConfirmDialog>
    <ConfirmDialog :open="!!plan" title="Plán importu" confirm-label="Potvrdit import" :confirm-disabled="busy || !!plan?.blockers.length" @confirm="performImport" @cancel="!busy && (plan = null)"><PlanView v-if="plan" :plan="plan" collapsed data-test="library-plan"><p v-if="plan.library">{{ typeof plan.library === 'string' ? plan.library : plan.library.name }}</p></PlanView></ConfirmDialog>
    <ConfirmDialog :open="!!seedPlan" title="Obnovit výchozí agenty a workflows" confirm-label="Obnovit" :confirm-disabled="busy || !!seedPlan?.blockers.length || !seedPlan?.files.length" @confirm="performSeed" @cancel="!busy && (seedPlan = null)">
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
  </section>
</template>
<style src="./library.css" />
