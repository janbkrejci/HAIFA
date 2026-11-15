<script setup lang="ts">
import { t } from '@/lib/i18n'
import { factoryDiagnostic, factoryErrorText } from '@/lib/factoryMessages'
// "Nastavení agentů" on the Factory tab: the repo-level harness, model and thinking of every
// agent (RosterEditor: inherited or overridden, override and "Vrátit na zděděné"). The intro
// names the library an agent without its own copy inherits from (GET .../factory/items). The
// workflows, skills and extensions and moving an own copy to the library are on the Knihovna page.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchFactoryItems } from '@/lib/api'
import { shortSha } from '@/lib/format'
import CollapsibleSection from '@/components/ui/CollapsibleSection.vue'
import RosterEditor from './RosterEditor.vue'

const props = defineProps<{ repoId: string; disabled?: boolean }>()
const emit = defineEmits<{ busy: [value: boolean]; success: [] }>()
const open = defineModel<boolean>('open', { default: true })
const library = ref<string | null>(null)
const libraryName = ref<string | null>(null)
const roster = ref<InstanceType<typeof RosterEditor> | null>(null)
const error = ref<unknown>('')
let generation = 0

async function load() {
  const mine = ++generation
  error.value = ''
  try {
    const data = await fetchFactoryItems(props.repoId)
    if (mine !== generation) return
    library.value = data.library
    libraryName.value = data.library_name ?? null
  } catch (e) {
    if (mine === generation) error.value = e
  }
}

/** Where an agent without its own copy comes from: the library by name and short commit, or the seed. */
const inheritText = computed(() => library.value
  ? t('factoryUi.inheritLibrary', { name: libraryName.value ?? t('factoryUi.library'), sha: shortSha(library.value) })
  : t('factoryUi.inheritSeed'))

async function reload() {
  await Promise.all([load(), roster.value?.reload()])
}

onMounted(load)
onBeforeUnmount(() => { ++generation; emit('busy', false) })
defineExpose({ reload })
</script>

<template>
  <CollapsibleSection v-model:open="open" :heading="t('factoryUi.agents')" class="items" data-test="repo-items">
    <p class="hint" data-test="items-inherit">{{ inheritText }}</p>
    <p v-if="error" role="alert" class="error" data-test="item-error">{{ factoryErrorText(error) }}</p>
    <details v-if="error"><summary>{{ t('factoryUi.technical') }}</summary>{{ factoryDiagnostic(error) }}</details>
    <RosterEditor ref="roster" :repo-id="repoId" :disabled="disabled" @busy="emit('busy', $event)" @saved="emit('success')" />
  </CollapsibleSection>
</template>

<style scoped>
.items { margin-top: 28px; }
.hint { margin: 0 0 8px; color: var(--dim); }
.error { color: var(--red); }
</style>
