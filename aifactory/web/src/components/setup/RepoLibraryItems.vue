<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ITEM_TABS, fetchInventory, fetchRepoItem, saveIgnore, 
  type RepoInventory, type RepoLibraryItem, type RepoItemDetail, type IgnoreRule } from '@/lib/library'
import type { FactoryItemType } from '@/lib/api'
import { errorText } from '@/lib/format'
import SelectMenu from '@/components/ui/SelectMenu.vue'

const props = defineProps<{ type: FactoryItemType; shared: { type: string; name: string }[] }>()
const emit = defineEmits<{ move: [item: RepoLibraryItem]; import: [path: string, type: FactoryItemType]; changed: [] }>()
const inventory = ref<RepoInventory | null>(null)
const repo = ref('')
const source = ref('')
const showIgnored = ref(false)
const selected = ref<RepoLibraryItem | null>(null)
const detail = ref<RepoItemDetail | null>(null)
const error = ref('')
const busy = ref(false)
const ruleMode = ref<IgnoreRule['mode']>('prefix')
const ruleValue = ref('')
const ruleType = ref<IgnoreRule['type']>('*')
let generation = 0
const rows = computed(() => inventory.value?.items.filter(i => i.type === props.type && (!repo.value || repo.value === i.repo)
  && (showIgnored.value || !i.ignored) && (!source.value || source.value === (isOverride(i) ? 'override' : 'repo'))) ?? [])
const repoOptions = computed(() => [
  { value: '', label: 'Všechna repa' },
  ...(inventory.value?.repos.map(r => ({ value: r.id, label: r.name })) ?? []),
])
const sourceOptions = [
  { value: '', label: 'Všechny zdroje' },
  { value: 'repo', label: 'Pouze v repu' },
  { value: 'override', label: 'Vlastní kopie sdílené položky' },
]
const ruleModeOptions = [
  { value: 'prefix', label: 'Prefix názvu' },
  { value: 'directory', label: 'Adresář' },
]
const ruleTypeOptions = [
  { value: '*', label: 'Všechny typy' },
  ...ITEM_TABS.map(t => ({ value: t.type, label: t.label })),
]
const ruleRepos = computed(() => inventory.value?.repos.filter(r => !repo.value || repo.value === r.id) ?? [])
function isOverride(i: RepoLibraryItem) { return i.movable && props.shared.some(s => s.type === i.type && s.name === i.name) }
function identity(i: RepoLibraryItem) { return `${i.repo}/${i.type}/${i.path}` }
async function load() {
  try { inventory.value = await fetchInventory() } catch (e) { error.value = errorText(e) }
}
async function open(i: RepoLibraryItem) {
  const mine = ++generation
  selected.value = i; detail.value = null; error.value = ''
  try { const value = await fetchRepoItem(i); if (mine === generation) detail.value = value }
  catch (e) { if (mine === generation) error.value = errorText(e) }
}
async function save(id: string, rules: IgnoreRule[]) {
  busy.value = true; error.value = ''
  try {
    inventory.value = await saveIgnore(id, rules)
    emit('changed')
    generation++; selected.value = null; detail.value = null
  } catch (e) { error.value = errorText(e) }
  finally { busy.value = false }
}
function ignore(i: RepoLibraryItem) {
  const rules = inventory.value?.repos.find(r => r.id === i.repo)?.rules ?? []
  return save(i.repo, [...rules, { type: i.type, mode: 'item', value: i.path }])
}
async function addRule() {
  if (!repo.value || !ruleValue.value.trim()) return
  const rules = inventory.value?.repos.find(r => r.id === repo.value)?.rules ?? []
  await save(repo.value, [...rules, { type: ruleType.value, mode: ruleMode.value, value: ruleValue.value.trim() }])
  ruleValue.value = ''
}
watch(() => props.type, () => { generation++; selected.value = null; detail.value = null })
watch(() => props.shared, load)
onBeforeUnmount(() => { generation++ })
onMounted(load)
</script>

<template>
  <section data-test="repo-library">
    <h3>Položky připojených repozitářů</h3>
    <p>Vlastní kopie a položky pouze v repu. Ignorování skryje položky jen v Knihovně a nabídce ke sdílení; běh ani soubory nemění.</p>
    <div class="filters">
      <label>Repo <SelectMenu v-model="repo" :options="repoOptions" label="Repo" data-test="inventory-repo" /></label>
      <label>Zdroj <SelectMenu v-model="source" :options="sourceOptions" label="Zdroj" data-test="inventory-source" /></label>
      <label><input v-model="showIgnored" type="checkbox" data-test="inventory-ignored" /> Zobrazit ignorované a pravidla</label>
      <button :disabled="busy" @click="load">Obnovit přehled</button>
    </div>
    <p v-if="error" role="alert">{{ error }}</p>
    <p v-for="e in inventory?.errors" :key="e.repo" role="alert">{{ e.repo_name }}: {{ e.message }}</p>
    <form v-if="repo" class="filters" @submit.prevent="addRule">
      <label>Hromadně ignorovat <SelectMenu v-model="ruleMode" :options="ruleModeOptions" label="Hromadně ignorovat" data-test="ignore-mode" /></label>
      <label>Typ <SelectMenu v-model="ruleType" :options="ruleTypeOptions" label="Typ" data-test="ignore-type" /></label>
      <label>Hodnota <input v-model="ruleValue" data-test="ignore-value" placeholder="bmad nebo .claude/skills/bmad" /></label>
      <button :disabled="busy || !ruleValue.trim()" data-test="ignore-add">Přidat pravidlo</button>
    </form>
    <template v-if="showIgnored">
      <div v-for="r in ruleRepos" :key="r.id" data-test="ignore-rules">
        <h4>{{ r.name }} · pravidla ignorování</h4>
        <p v-if="!r.rules.length">Žádná pravidla</p>
        <p v-for="(rule, index) in r.rules" :key="index">{{ rule.type }} · {{ rule.mode }} · {{ rule.value }} <button :disabled="busy" data-test="ignore-restore" @click="save(r.id, r.rules.filter((_, n) => n !== index))">Zrušit pravidlo a obnovit položky</button></p>
      </div>
    </template>
    <ul class="repo-items" data-test="inventory-items">
      <li v-for="i in rows" :key="identity(i)" data-test="inventory-item">
        <button @click="open(i)">{{ i.type }} · {{ i.name }}</button>
        <span>{{ i.repo_name }} · {{ i.path }} · {{ isOverride(i) ? 'Vlastní kopie sdílené položky' : 'Pouze v repu' }}{{ i.ignored ? ' · Ignorováno' : '' }}</span>
        <button v-if="!i.ignored" :disabled="busy" data-test="inventory-hide" @click="ignore(i)">Skrýt</button>
        <span v-else>Zruš odpovídající pravidla pro obnovení.</span>
      </li>
    </ul>
    <p v-if="!rows.length">Žádné odpovídající položky repozitářů.</p>
    <section v-if="selected && detail" data-test="inventory-detail">
      <h4>{{ selected.repo_name }} · {{ selected.type }}/{{ selected.name }}</h4>
      <p>{{ selected.path }}</p>
      <template v-if="!selected.ignored">
        <button v-if="detail.movable" data-test="inventory-move" @click="emit('move', selected)">Diff / přesunout do knihovny</button>
        <button v-if="selected.type === 'skill'" data-test="inventory-import" @click="emit('import', detail.absolute_path, selected.type)">Importovat do knihovny</button>
      </template>
      <details v-for="f in detail.files" :key="f.path"><summary>{{ f.path }}</summary><pre>{{ f.binary ? 'Binární soubor' : f.content }}</pre></details>
    </section>
  </section>
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin: 12px 0; }
.repo-items { padding-left: 0; list-style: none; }
.repo-items li { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border-soft); }
.repo-items span { overflow-wrap: anywhere; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; }
</style>
