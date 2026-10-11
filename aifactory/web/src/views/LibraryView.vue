<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { FactoryItemType } from '@/lib/api'
import { ITEM_TABS, fetchLibrary, fetchItem, previewLibrary, applyLibrary, versionLabel,
  type LibraryStatus, type LibraryItem, type ItemDetail, type LibraryPlan, type LibraryRequest } from '@/lib/library'
import { errorText } from '@/lib/format'
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
let generation = 0
const items = computed(() => library.value?.items?.filter(i => i.type === tab.value) ?? [])
/** An older revision is open: repos inherit the current one. */
const oldVersion = computed(() => !!detail.value && !!currentItem.value && detail.value.version !== currentItem.value.version)
async function load() {
  busy.value = true
  try { library.value = await fetchLibrary() }
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
function close() { generation++; detail.value = null; currentItem.value = null; loadingDetail.value = false }
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
        <thead><tr><th>Jméno</th><th>Účel / popis</th><th>Verze</th><th>Datum</th><th>Autor</th></tr></thead>
        <tbody><tr v-for="item in items" :key="item.name" data-test="library-item">
          <td><button :disabled="busy" @click="open(item)">{{ item.name }}</button></td><td>{{ item.purpose || item.description || '—' }}</td>
          <td>{{ versionLabel(item) }}</td><td>{{ item.date }}</td><td>{{ item.author }}</td>
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
      <p>Repa bez vlastní kopie dědí aktuální verzi knihovny.</p>
      <p v-if="oldVersion" class="warning" data-test="item-old-version">Prohlížíš starší verzi. <button :disabled="busy || loadingDetail" @click="open(currentItem!)">Zobrazit aktuální verzi</button></p>
    </section>
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
