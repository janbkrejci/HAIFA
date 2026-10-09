<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchRepos, type FactoryItemType, type RepoItem } from '@/lib/api'
import { ITEM_TABS, fetchLibrary, fetchItem, previewLibrary, applyLibrary, previewRepos, applyRepo, stateText, versionLabel,
  type LibraryStatus, type LibraryItem, type ItemDetail, type LibraryPlan, type LibraryRequest, type RepoPlanRow } from '@/lib/library'
import { errorText } from '@/lib/format'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import PlanView from '@/components/factory/PlanView.vue'
import DiffContent from '@/components/review/DiffContent.vue'
const tab = ref<FactoryItemType>('agent')
const library = ref<LibraryStatus | null>(null)
const detail = ref<ItemDetail | null>(null)
const currentItem = ref<LibraryItem | null>(null)
const repos = ref<RepoItem[]>([])
const selected = ref<string[]>([])
const target = ref<'base' | 'pr'>('base')
const action = ref<'add' | 'update'>('add')
const selecting = ref(false)
const rows = ref<RepoPlanRow[] | null>(null)
const results = ref<{ id: string; name: string; text: string; pr?: string }[]>([])
const diff = ref<RepoPlanRow | null>(null)
const busy = ref(false)
const loadingDetail = ref(false)
const error = ref('')
const importing = ref(false)
const path = ref('')
const importType = ref<FactoryItemType>('skill')
const plan = ref<LibraryPlan | null>(null)
const importRequest = ref<LibraryRequest | null>(null)
const importResult = ref('')
let generation = 0
const items = computed(() => library.value?.items?.filter(i => i.type === tab.value) ?? [])
/** An older revision is open: operations in repos always use the current one, so they are off. */
const oldVersion = computed(() => !!detail.value && !!currentItem.value && detail.value.version !== currentItem.value.version)
const usable = computed(() => rows.value?.filter(r => r.status === 'planned' && r.plan && !r.plan.blockers.length) ?? [])
async function load() {
  busy.value = true
  try { const [lib, registered] = await Promise.all([fetchLibrary(), fetchRepos()]); library.value = lib; repos.value = registered.repos }
  catch (e) { error.value = errorText(e) }
  finally { busy.value = false }
}
async function open(item: LibraryItem, version?: string) {
  const mine = ++generation
  if (currentItem.value?.name !== item.name || currentItem.value?.type !== item.type) detail.value = null
  loadingDetail.value = true; error.value = ''; currentItem.value = item
  try { const value = await fetchItem(item.type, item.name, version); if (mine === generation) detail.value = value }
  catch (e) { if (mine === generation) error.value = errorText(e) }
  finally { if (mine === generation) loadingDetail.value = false }
}
function close() { generation++; detail.value = null; currentItem.value = null; loadingDetail.value = false; selected.value = []; diff.value = null }
function changeTab(type: FactoryItemType) { tab.value = type; close(); results.value = [] }
function startAdd() { action.value = 'add'; selecting.value = true; selected.value = []; results.value = [] }
async function planRepos() {
  if (busy.value || !currentItem.value || !selected.value.length) return
  busy.value = true; error.value = ''; results.value = []
  try { rows.value = (await previewRepos(action.value, currentItem.value, [...new Set(selected.value)], target.value)).repos; selecting.value = false }
  catch (e) { error.value = errorText(e) }
  finally { busy.value = false }
}
async function performRepos() {
  if (busy.value || !usable.value.length) return
  busy.value = true; error.value = ''
  const reviewed = rows.value ?? []
  rows.value = null; results.value = []
  for (const row of reviewed) {
    if (row.status !== 'planned' || !row.plan || row.plan.blockers.length) {
      results.value.push({ id: row.repo.id, name: row.repo.name, text: 'Blokátor: ' + (row.error?.message ?? row.plan?.blockers.map(b => b.message).join('; ') ?? row.status) })
      continue
    }
    try {
      const result = await applyRepo(row)
      results.value.push({ id: row.repo.id, name: row.repo.name, text: `Dokončeno · commit ${result.commit ?? result.after ?? 'beze změny'}${result.warnings?.length ? ' · ' + result.warnings.join('; ') : ''}`, pr: result.pr?.url })
    } catch (e) { results.value.push({ id: row.repo.id, name: row.repo.name, text: 'Blokátor: ' + errorText(e) }) }
  }
  busy.value = false
  await load()
  if (currentItem.value) await open(currentItem.value)
}
async function showDiff(id: string) {
  if (!currentItem.value || busy.value) return
  busy.value = true; error.value = ''
  try { diff.value = (await previewRepos('update', currentItem.value, [id], target.value)).repos[0] ?? null }
  catch (e) { error.value = errorText(e) }
  finally { busy.value = false }
}
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
onMounted(() => { void load() })
onBeforeUnmount(() => { generation++ })
</script>
<template>
  <section class="global-page" data-test="library">
    <header><h1>Knihovna</h1><button :disabled="busy || !library?.exists" data-test="library-import" @click="importing = true">Import…</button></header>
    <p v-if="error" role="alert">{{ error }}</p><p v-if="importResult" role="status">{{ importResult }}</p>
    <p v-if="busy || loadingDetail">Načítám…</p>
    <p v-if="library && !library.exists">Knihovna není nastavená. <a href="#/setup">Nastavit na tomto počítači</a></p>
    <div role="tablist" aria-label="Typ položek">
      <button v-for="t in ITEM_TABS" :key="t.type" role="tab" :aria-selected="tab === t.type" :disabled="busy" :data-test="'tab-' + t.type" @click="changeTab(t.type)">{{ t.label }}</button>
    </div>
    <template v-if="!currentItem">
      <div class="table-scroll"><table data-test="library-items">
        <thead><tr><th>Jméno</th><th>Účel / popis</th><th>Verze</th><th>Datum</th><th>Autor</th><th>Použití</th></tr></thead>
        <tbody><tr v-for="item in items" :key="item.name" data-test="library-item">
          <td><button :disabled="busy" @click="open(item)">{{ item.name }}</button></td><td>{{ item.purpose || item.description || '—' }}</td>
          <td>{{ versionLabel(item) }}</td><td>{{ item.date }}</td><td>{{ item.author }}</td>
          <td><span v-for="usage in item.repos?.filter(r => r.slot !== null) ?? []" :key="usage.repo.id + usage.slot" class="chip" :class="usage.state">{{ usage.repo.name }} · {{ stateText(usage.state) }}</span></td>
        </tr></tbody>
      </table></div><p v-if="library?.exists && !items.length">Žádné položky tohoto typu</p>
    </template>
    <section v-else-if="detail" data-test="library-detail">
      <button :disabled="busy" @click="close">Zpět na položky</button>
      <h2>{{ detail.name }} · {{ versionLabel({ ...detail, n: detail.history.find(h => h.version === detail?.version)?.n }) }}</h2>
      <p>{{ detail.purpose || detail.description }}</p>
      <h3>Soubory · jen čtení</h3>
      <details v-for="file in detail.files" :key="file.path" data-test="item-file"><summary>{{ file.path }}</summary><pre>{{ file.binary ? 'Binární soubor' : file.content }}</pre></details>
      <h3>Historie verzí</h3>
      <ul data-test="item-history"><li v-for="rev in detail.history" :key="rev.version"><button :disabled="busy || loadingDetail" @click="open(currentItem!, rev.version)">{{ versionLabel(rev) }}</button> · {{ rev.date }} · {{ rev.author }}</li></ul>
      <p>Operace v repech používají aktuální verzi knihovny.</p>
      <p v-if="oldVersion" class="warning" data-test="item-old-version">Prohlížíš starší verzi. Přidat ani aktualizovat ji nejde, operace použijí aktuální verzi. <button :disabled="busy || loadingDetail" @click="open(currentItem!)">Zobrazit aktuální verzi</button></p>
      <label>Cíl <SelectMenu v-model="target" label="Cíl operace" data-test="item-target" :disabled="busy || oldVersion" :options="[{ value: 'base', label: 'Commit do base' }, { value: 'pr', label: 'Pull request' }]" /></label>
      <button :disabled="busy || oldVersion" data-test="item-add" @click="startAdd">Přidat do repozitářů…</button>
      <button :disabled="busy || oldVersion || !selected.length" data-test="item-update" @click="action = 'update'; planRepos()">Aktualizovat vybraná repa…</button>
      <div class="table-scroll"><table data-test="item-usage"><thead><tr><th>Vybrat</th><th>Repo</th><th>Slot</th><th>Stav</th><th>Verze</th><th>Diff</th></tr></thead><tbody>
        <tr v-for="usage in detail.repos" :key="usage.repo.id + usage.slot"><td><input v-model="selected" type="checkbox" :value="usage.repo.id" :disabled="busy || oldVersion" :aria-label="'Vybrat ' + usage.repo.name" /></td><td>{{ usage.repo.name }}</td><td>{{ usage.slot ?? '—' }}</td><td><span class="chip" :class="usage.state">{{ stateText(usage.state) }}</span></td><td>{{ versionLabel(usage) }}</td><td><button :disabled="busy || !usage.slot" @click="showDiff(usage.repo.id)">Diff</button></td></tr>
      </tbody></table></div>
      <section v-if="diff" data-test="item-diff"><h3>Diff · {{ diff.repo.name }}</h3><button @click="diff = null">Zavřít diff</button>
        <p v-if="diff.error" role="alert">{{ diff.error.message }}</p>
        <PlanView v-if="diff.plan" :plan="diff.plan" collapsed data-test="library-plan" />
        <template v-for="item in diff.plan?.update?.items ?? []" :key="item.type + item.name"><details v-for="file in item.files" :key="file.file"><summary>{{ file.file }}</summary><DiffContent :patch="file.diff ?? file.ours_diff ?? file.theirs_diff ?? ''" :binary="false" /></details></template>
      </section>
    </section>
    <ul data-test="repo-results"><li v-for="(r, index) in results" :key="r.id + index">{{ r.name }} · {{ r.text }} <a v-if="r.pr" :href="r.pr" target="_blank" rel="noopener">PR</a></li></ul>
    <ConfirmDialog :open="selecting" title="Přidat do repozitářů" confirm-label="Náhled plánů" :confirm-disabled="busy || !selected.length" @confirm="planRepos" @cancel="!busy && (selecting = false)">
      <p v-if="error" role="alert">{{ error }}</p>
      <p>Každé repo bude provedeno samostatně · {{ target === 'pr' ? 'Pull request' : 'Commit do base' }}</p>
      <label v-for="repo in repos" :key="repo.id" class="repo-option"><input v-model="selected" type="checkbox" :value="repo.id" :disabled="busy" /> {{ repo.name }} · {{ repo.path }}</label>
    </ConfirmDialog>
    <ConfirmDialog :open="!!rows" title="Plány pro repozitáře" confirm-label="Provést dostupné plány" :confirm-disabled="busy || !usable.length" @confirm="performRepos" @cancel="!busy && (rows = null)">
      <section v-for="row in rows ?? []" :key="row.repo.id" data-test="repo-plan"><h3>{{ row.repo.name }} · {{ stateText(row.status) }}</h3><p v-if="row.error" role="alert">{{ row.error.message }}</p><PlanView v-if="row.plan" :plan="row.plan" collapsed data-test="library-plan"><p>{{ row.plan.action === 'add' ? 'Přidání položky' : 'Aktualizace položky' }} · {{ row.plan.apply_target === 'pr' ? 'Pull request' : 'Commit do base' }}{{ row.plan.base ? ' · ' + row.plan.base : '' }}</p></PlanView></section>
    </ConfirmDialog>
    <ConfirmDialog :open="importing" title="Import do knihovny" confirm-label="Náhled plánu" :confirm-disabled="busy || !path.trim()" @confirm="planImport" @cancel="!busy && (importing = false)">
      <p v-if="error" role="alert">{{ error }}</p>
      <p>Složka musí být pod domovskou složkou uživatele.</p>
      <label>Složka <input v-model="path" data-test="import-path" :disabled="busy" placeholder="~/moje-skilly/demo" /></label>
      <label>Typ <SelectMenu v-model="importType" label="Typ importované položky" data-test="import-type" :disabled="busy" :options="ITEM_TABS.map(t => ({ value: t.type, label: t.label }))" /></label>
    </ConfirmDialog>
    <ConfirmDialog :open="!!plan" title="Plán importu" confirm-label="Potvrdit import" :confirm-disabled="busy || !!plan?.blockers.length" @confirm="performImport" @cancel="!busy && (plan = null)"><PlanView v-if="plan" :plan="plan" collapsed data-test="library-plan"><p v-if="plan.library">{{ typeof plan.library === 'string' ? plan.library : plan.library.name }}</p></PlanView></ConfirmDialog>
  </section>
</template>
<style src="./library.css" />
<style scoped>
.repo-option { display: block; margin: 10px 0; }
</style>
