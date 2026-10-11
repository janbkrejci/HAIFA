<script setup lang="ts">
// The repo's agents, workflows, skills and extensions (GET .../factory/items): inherited from the
// library, or the repo's own copy in .factory/ that wins. An own copy can move to the library:
// a reviewed plan (repo files and library files) applied with its digest after a confirmation.
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError, applyMove, fetchFactoryItems, previewMove, type FactoryMovePlan, type FactoryRepoItem } from '@/lib/api'
import { ITEM_TABS } from '@/lib/library'
import { planCodeText } from '@/lib/factory'
import { errorText, shortSha } from '@/lib/format'
import PlanView from './PlanView.vue'
import ConfirmDialog from '@/components/ui/ConfirmDialog.vue'

const props = defineProps<{ repoId: string; disabled?: boolean }>()
const emit = defineEmits<{ busy: [value: boolean]; success: [] }>()
const items = ref<FactoryRepoItem[]>([])
const library = ref<string | null>(null)
const loading = ref(false)
const error = ref('')
const result = ref('')
const moving = ref<FactoryRepoItem | null>(null)
const plan = ref<FactoryMovePlan | null>(null)
const working = ref(false)
const confirm = ref(false)
let generation = 0

async function load() {
  const mine = ++generation
  loading.value = true
  error.value = ''
  try {
    const data = await fetchFactoryItems(props.repoId)
    if (mine !== generation) return
    items.value = data.items
    library.value = data.library
  } catch (e) {
    if (mine === generation) error.value = errorText(e)
  } finally {
    if (mine === generation) loading.value = false
  }
}

function close() { moving.value = null; plan.value = null; confirm.value = false; error.value = '' }

async function preview(item: FactoryRepoItem) {
  if (working.value || props.disabled) return
  close()
  result.value = ''
  moving.value = item
  working.value = true
  try {
    plan.value = await previewMove({ type: item.type, name: item.name }, props.repoId)
  } catch (e) {
    error.value = e instanceof ApiError ? `${planCodeText(e.code)}: ${e.message}` : errorText(e)
  } finally {
    working.value = false
  }
}

async function apply() {
  const item = moving.value
  if (!item || !plan.value || plan.value.blockers.length || working.value) return
  confirm.value = false
  working.value = true
  error.value = ''
  try {
    const done = await applyMove({ type: item.type, name: item.name }, plan.value.digest, props.repoId)
    result.value = `${item.type}/${item.name} je v knihovně${done.library_commit ? ` (${shortSha(done.library_commit)})` : ''}.`
    close()
    await load()
    emit('success')
  } catch (e) {
    error.value = e instanceof ApiError ? `${planCodeText(e.code)}: ${e.message}` : errorText(e)
  } finally {
    working.value = false
  }
}

watch(moving, value => emit('busy', !!value))
onMounted(load)
onBeforeUnmount(() => { ++generation; emit('busy', false) })
defineExpose({ reload: load })
</script>

<template>
  <section class="items" data-test="repo-items">
    <h2>Položky repa</h2>
    <p class="hint">Bez vlastní kopie v .factory/ se položka dědí z knihovny<template v-if="library"> {{ library }}</template>.</p>
    <p v-if="loading && !items.length" class="hint">Načítám položky…</p>
    <p v-if="error" role="alert" class="error" data-test="item-error">{{ error }}</p>
    <p v-if="result" class="ok" data-test="item-result">{{ result }}</p>
    <section v-for="tab in ITEM_TABS" :key="tab.type">
      <h3>{{ tab.label }}</h3>
      <ul v-if="items.some(i => i.type === tab.type)">
        <li v-for="item in items.filter(i => i.type === tab.type)" :key="item.name" :data-test="`item-${item.type}-${item.name}`">
          <span class="mono">{{ item.name }}</span>
          <span class="tag" :data-origin="item.origin">{{ item.origin === 'repo' ? 'vlastní kopie' : 'z knihovny' }}</span>
          <button v-if="item.origin === 'repo'" type="button" class="btn" :disabled="disabled || working || !!moving"
            :data-test="`item-move-${item.type}-${item.name}`" @click="preview(item)">Přesunout do knihovny</button>
        </li>
      </ul>
      <p v-else class="hint">Bez položek</p>
    </section>
    <section v-if="moving" class="operation" data-test="item-move-plan">
      <h3>Přesunout {{ moving.type }}/{{ moving.name }} do knihovny</h3>
      <p v-if="working && !plan" class="hint">Načítám plán…</p>
      <template v-if="plan">
        <PlanView :plan="plan" collapsed data-test="move-repo-plan"><h4>Repo · commit do {{ plan.base }}</h4></PlanView>
        <PlanView :plan="plan.library_plan" collapsed data-test="move-library-plan"><h4>Knihovna<template v-if="plan.library"> · {{ shortSha(plan.library) }}</template></h4></PlanView>
      </template>
      <div class="actions">
        <button type="button" class="btn" :disabled="working || !plan || !!plan.blockers.length" data-test="item-move-apply" @click="confirm = true">Provést</button>
        <button type="button" class="btn" :disabled="working" data-test="item-move-close" @click="close">Zavřít</button>
      </div>
    </section>
    <ConfirmDialog :open="confirm" :title="`Přesunout ${moving?.type}/${moving?.name} do knihovny?`"
      message="Zapíše položku do knihovny, smaže ji z repa a commitne obojí." confirm-label="Přesunout"
      :confirm-disabled="working || !plan" @cancel="confirm = false" @confirm="apply" />
  </section>
</template>

<style scoped>
.items { margin: 24px 0; }
h2 { margin: 0 0 8px; color: var(--dim); font-size: 14px; font-weight: 600; letter-spacing: 0.04em; text-transform: uppercase; }
h3 { margin: 14px 0 6px; font-size: 15px; }
ul { margin: 0; padding: 0; list-style: none; }
li { display: flex; align-items: center; gap: 10px; padding: 4px 0; }
.tag { padding: 0 6px; border: 1px solid var(--border); border-radius: 6px; color: var(--dim); font-size: 12px; }
.tag[data-origin='repo'] { color: var(--purple); }
.hint { color: var(--dim); }
.btn { padding: 4px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel-2); color: var(--text); font: inherit; font-size: 13px; cursor: pointer; }
.btn:disabled { cursor: default; opacity: 0.5; }
.operation { margin-top: 16px; padding: 16px; border: 1px solid var(--border); border-radius: 10px; }
.actions { display: flex; gap: 8px; margin-top: 10px; }
.error { color: var(--red); }
.ok { color: var(--green); }
</style>
