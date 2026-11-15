<script setup lang="ts">
import { t } from '@/lib/i18n'
import { setupErrorText } from '@/lib/setupMessages'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ITEM_TABS, fetchInventory, fetchRepoItem, saveIgnore, 
  type RepoInventory, type RepoLibraryItem, type RepoItemDetail, type IgnoreRule } from '@/lib/library'
import type { FactoryItemType } from '@/lib/api'
import SelectMenu from '@/components/ui/SelectMenu.vue'

const props = defineProps<{ type: FactoryItemType; shared: { type: string; name: string }[] }>()
const emit = defineEmits<{ move: [item: RepoLibraryItem]; import: [path: string, type: FactoryItemType]; changed: [] }>()
const inventory = ref<RepoInventory | null>(null)
const repo = ref('')
const source = ref('')
const showIgnored = ref(false)
const selected = ref<RepoLibraryItem | null>(null)
const detail = ref<RepoItemDetail | null>(null)
const error = ref<unknown>(null)
const busy = ref(false)
const ruleMode = ref<IgnoreRule['mode']>('prefix')
const ruleValue = ref('')
const ruleType = ref<IgnoreRule['type']>('*')
let generation = 0
const rows = computed(() => inventory.value?.items.filter(i => i.type === props.type && (!repo.value || repo.value === i.repo)
  && (showIgnored.value || !i.ignored) && (!source.value || source.value === (isOverride(i) ? 'override' : 'repo'))) ?? [])
const repoOptions = computed(() => [
  { value: '', label: t('setup.allRepos') },
  ...(inventory.value?.repos.map(r => ({ value: r.id, label: r.name })) ?? []),
])
const sourceOptions = computed(() => [
  { value: '', label: t('setup.allSources') },
  { value: 'repo', label: t('setup.repoOnly') },
  { value: 'override', label: t('setup.ownCopy') },
])
const ruleModeOptions = computed(() => [
  { value: 'prefix', label: t('setup.namePrefix') },
  { value: 'directory', label: t('setup.directory') },
])
const ruleTypeOptions = computed(() => [
  { value: '*', label: t('setup.allTypes') },
  ...ITEM_TABS.map(tab => ({ value: tab.type, label: t(tab.label) })),
])
const ruleRepos = computed(() => inventory.value?.repos.filter(r => !repo.value || repo.value === r.id) ?? [])
function isOverride(i: RepoLibraryItem) { return i.movable && props.shared.some(s => s.type === i.type && s.name === i.name) }
function identity(i: RepoLibraryItem) { return `${i.repo}/${i.type}/${i.path}` }
async function load() {
  try { inventory.value = await fetchInventory() } catch (e) { error.value = e }
}
async function open(i: RepoLibraryItem) {
  const mine = ++generation
  selected.value = i; detail.value = null; error.value = null
  try { const value = await fetchRepoItem(i); if (mine === generation) detail.value = value }
  catch (e) { if (mine === generation) error.value = e }
}
async function save(id: string, rules: IgnoreRule[]) {
  busy.value = true; error.value = null
  try {
    inventory.value = await saveIgnore(id, rules)
    emit('changed')
    generation++; selected.value = null; detail.value = null
  } catch (e) { error.value = e }
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
    <h3>{{ t('setup.repoItems') }}</h3>
    <p>{{ t('setup.repoItemsHint') }}</p>
    <div class="filters">
      <label>Repo <SelectMenu v-model="repo" :options="repoOptions" label="Repo" data-test="inventory-repo" /></label>
      <label>{{ t('setup.source') }} <SelectMenu v-model="source" :options="sourceOptions" :label="t('setup.source')" data-test="inventory-source" /></label>
      <label><input v-model="showIgnored" type="checkbox" data-test="inventory-ignored" /> {{ t('setup.showIgnored') }}</label>
      <button :disabled="busy" @click="load">{{ t('setup.refreshInventory') }}</button>
    </div>
    <p v-if="error" role="alert">{{ setupErrorText(error) }}</p><details v-if="error"><summary>{{ t('dashboard.diagnostics') }}</summary>{{ String(error) }}</details>
    <div v-for="e in inventory?.errors" :key="e.repo" role="alert">{{ t('setup.repoReadError', { repo: e.repo_name }) }}<details><summary>{{ t('dashboard.diagnostics') }}</summary>{{ e.repo_name }}: {{ e.message }}</details></div>
    <form v-if="repo" class="filters" @submit.prevent="addRule">
      <label>{{ t('setup.bulkIgnore') }} <SelectMenu v-model="ruleMode" :options="ruleModeOptions" :label="t('setup.bulkIgnore')" data-test="ignore-mode" /></label>
      <label>{{ t('setup.type') }} <SelectMenu v-model="ruleType" :options="ruleTypeOptions" :label="t('setup.type')" data-test="ignore-type" /></label>
      <label>{{ t('setup.value') }} <input v-model="ruleValue" data-test="ignore-value" :placeholder="t('setup.ruleExample')" /></label>
      <button :disabled="busy || !ruleValue.trim()" data-test="ignore-add">{{ t('setup.addRule') }}</button>
    </form>
    <template v-if="showIgnored">
      <div v-for="r in ruleRepos" :key="r.id" data-test="ignore-rules">
        <h4>{{ r.name }} · {{ t('setup.ignoreRules') }}</h4>
        <p v-if="!r.rules.length">{{ t('setup.noRules') }}</p>
        <p v-for="(rule, index) in r.rules" :key="index">{{ rule.type }} · {{ rule.mode }} · {{ rule.value }} <button :disabled="busy" data-test="ignore-restore" @click="save(r.id, r.rules.filter((_, n) => n !== index))">{{ t('setup.removeRule') }}</button></p>
      </div>
    </template>
    <ul class="repo-items" data-test="inventory-items">
      <li v-for="i in rows" :key="identity(i)" data-test="inventory-item">
        <button @click="open(i)">{{ i.type }} · {{ i.name }}</button>
        <span>{{ i.repo_name }} · {{ i.path }} · {{ isOverride(i) ? t('setup.ownCopy') : t('setup.repoOnly') }}{{ i.ignored ? t('setup.ignored') : '' }}</span>
        <button v-if="!i.ignored" :disabled="busy" data-test="inventory-hide" @click="ignore(i)">{{ t('setup.hide') }}</button>
        <span v-else>{{ t('setup.restoreRulesHint') }}</span>
      </li>
    </ul>
    <p v-if="!rows.length">{{ t('setup.noRepoItems') }}</p>
    <section v-if="selected && detail" data-test="inventory-detail">
      <h4>{{ selected.repo_name }} · {{ selected.type }}/{{ selected.name }}</h4>
      <p>{{ selected.path }}</p>
      <template v-if="!selected.ignored">
        <button v-if="detail.movable" data-test="inventory-move" @click="emit('move', selected)">{{ t('setup.diffMove') }}</button>
        <button v-if="selected.type === 'skill'" data-test="inventory-import" @click="emit('import', detail.absolute_path, selected.type)">{{ t('setup.importLibrary') }}</button>
      </template>
      <details v-for="f in detail.files" :key="f.path"><summary>{{ f.path }}</summary><pre>{{ f.binary ? t('setup.binary') : f.content }}</pre></details>
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
