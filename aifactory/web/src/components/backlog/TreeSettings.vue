<script setup lang="ts">
// The Nastavení panel of a project or step under its tree row: the auto-continue and
// auto-merge switches (`factory backlog auto-continue|auto-merge`) and the other keys of its
// `index.md` with their inherited values (`factory backlog edit`, ContainerSettings). The
// switches own `auto_continue` and `auto_merge`, so the form leaves them out: one place per
// value. Every write goes to the working tree and asks the tree to load again.
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  autoMode,
  editContainer,
  fetchContainer,
  flattenIssues,
  isContainerDetail,
  setAutoContinue,
  setAutoMerge,
  takeScroll,
  type AutoMode,
  type ContainerDetailData,
  type ContainerNode,
  type EditContainerInput,
  type WriteError,
} from '@/lib/backlog'
import AutoContinueToggle from './AutoContinueToggle.vue'
import ContainerSettings from './ContainerSettings.vue'

const props = defineProps<{ node: ContainerNode & { id: string }; workflows: string[] }>()
const emit = defineEmits<{ changed: [] }>()

/** Keys the switches above the form write. */
const SWITCH_KEYS = ['auto_continue', 'auto_merge']

type SwitchKey = 'auto' | 'merge'
const pending = ref<{ key: SwitchKey; mode: AutoMode } | null>(null)
const switchError = ref<string | null>(null)

const root = ref<HTMLElement | null>(null)
const detail = ref<ContainerDetailData | null>(null)
const loadError = ref<string | null>(null)
const saving = ref(false)
const saveError = ref<WriteError | null>(null)
const busy = computed(() => saving.value || pending.value !== null)

const editableKeys = computed(() => (detail.value?.editable_keys ?? []).filter((k) => !SWITCH_KEYS.includes(k)))
/** Key of the form: a saved or reloaded change resets it. */
const formKey = computed(() => {
  const c = detail.value?.container
  return c ? JSON.stringify([c.id, c.title, c.own, c.effective]) : ''
})

async function load() {
  try {
    const next = await fetchContainer(props.node.id)
    detail.value = isContainerDetail(next) ? next : null
    loadError.value = detail.value ? null : `Nastavení ${props.node.id} se nepodařilo načíst.`
  } catch (e) {
    detail.value = null
    loadError.value = `Nastavení ${props.node.id} se nepodařilo načíst: ${flattenIssues(e).message}`
  }
}

onMounted(async () => {
  await load()
  // opened from the graph page: show the whole panel once it has its height
  if (detail.value && takeScroll(props.node.id)) {
    await nextTick()
    root.value?.scrollIntoView?.({ block: 'start' })
  }
})

async function setSwitch(key: SwitchKey, mode: AutoMode) {
  pending.value = { key, mode }
  switchError.value = null
  try {
    if (key === 'auto') await setAutoContinue(props.node.id, mode)
    else await setAutoMerge(props.node.id, mode)
    emit('changed')
    void load()
  } catch (e) {
    switchError.value = flattenIssues(e).message
  } finally {
    pending.value = null
  }
}

async function onSave(input: EditContainerInput) {
  saving.value = true
  saveError.value = null
  try {
    const result = await editContainer(props.node.id, input)
    if (detail.value) detail.value = { ...detail.value, container: result.container }
    emit('changed')
  } catch (e) {
    saveError.value = flattenIssues(e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div ref="root" class="tree-settings" data-test="settings-panel" :data-container="node.id">
    <div class="switches" data-test="switches-panel">
      <AutoContinueToggle
        :mode="autoMode(node.auto_continue)"
        :effective="node.effective_auto_continue ?? false"
        :busy="busy"
        :pending="pending?.key === 'auto' ? pending.mode : null"
        @change="setSwitch('auto', $event)"
      />
      <AutoContinueToggle
        label="Auto-merge"
        test-prefix="merge"
        hint="workflow bez review se automaticky nemerguje"
        :mode="autoMode(node.auto_merge)"
        :effective="node.effective_auto_merge ?? false"
        :busy="busy"
        :pending="pending?.key === 'merge' ? pending.mode : null"
        @change="setSwitch('merge', $event)"
      />
      <p v-if="switchError" class="warn" data-test="switches-error">{{ switchError }}</p>
    </div>
    <ContainerSettings
      v-if="detail"
      :key="formKey"
      :container="detail.container"
      :editable-keys="editableKeys"
      :workflows="workflows"
      :busy="busy"
      :pending="saving"
      :error="saveError"
      @save="onSave"
    />
    <p v-else-if="loadError" class="warn" data-test="settings-error">{{ loadError }}</p>
    <p v-else class="faint" data-test="settings-loading">Načítám nastavení…</p>
  </div>
</template>

<style scoped>
.tree-settings {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding-top: 10px;
  padding-bottom: 12px;
  padding-right: 12px;
  border-bottom: 1px solid var(--border-soft);
  background: var(--panel-2);
  font-weight: 400;
}

.switches {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 28px;
}

.warn {
  margin: 0;
  color: var(--amber);
  font-size: 13px;
}

.faint {
  margin: 0;
}
</style>
