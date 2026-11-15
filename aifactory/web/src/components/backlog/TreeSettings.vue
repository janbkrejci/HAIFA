<script setup lang="ts">
import { t } from '@/lib/i18n'
import { backlogError } from '@/lib/backlogMessages'
// Backlog metadata only. Operating choices live on the Overview for this machine.
import { computed, nextTick, onMounted, ref } from 'vue'
import {
  editContainer,
  fetchContainer,
  flattenIssues,
  isContainerDetail,
  takeScroll,
  type ContainerDetailData,
  type ContainerNode,
  type EditContainerInput,
  type WriteError,
} from '@/lib/backlog'
import ContainerSettings from './ContainerSettings.vue'

const props = defineProps<{ node: ContainerNode & { id: string }; workflows: string[] }>()
const emit = defineEmits<{ changed: [] }>()

const root = ref<HTMLElement | null>(null)
const detail = ref<ContainerDetailData | null>(null)
const loadError = ref<(() => string) | null>(null)
const saving = ref(false)
const saveError = ref<WriteError | null>(null)
const busy = computed(() => saving.value)

const editableKeys = computed(() => (detail.value?.editable_keys ?? []).filter((k) => !['auto_continue', 'auto_merge', 'harness'].includes(k)))
/** Key of the form: a saved or reloaded change resets it. */
const formKey = computed(() => {
  const c = detail.value?.container
  return c ? JSON.stringify([c.id, c.title, c.own, c.effective]) : ''
})

async function load() {
  try {
    const next = await fetchContainer(props.node.id)
    detail.value = isContainerDetail(next) ? next : null
    loadError.value = detail.value ? null : () => t('backlog.nastaveni_p0_se_nepodarilo_nacist', { p0: props.node.id })
  } catch (e) {
    detail.value = null
    loadError.value = () => t('backlog.nastaveni_p0_se_nepodarilo_nacist_p1', { p0: props.node.id, p1: backlogError(flattenIssues(e)) })
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
    <p class="faint">{{ t('backlog.automatizace_a_vychozi_harness_nove_factory_se_nastavuji_na_prehledu_na_tom') }}</p>
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
    <p v-else-if="loadError" class="warn" data-test="settings-error">{{ loadError() }}</p>
    <p v-else class="faint" data-test="settings-loading">{{ t('backlog.nacitam_nastaveni') }}</p>
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
