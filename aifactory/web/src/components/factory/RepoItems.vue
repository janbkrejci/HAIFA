<script setup lang="ts">
// "Nastavení agentů" on the Factory tab: the repo-level harness, model and thinking of every
// agent (RosterEditor: inherited or overridden, override and "Vrátit na zděděné"). The intro
// names the library an agent without its own copy inherits from (GET .../factory/items). The
// workflows, skills and extensions and moving an own copy to the library are on the Knihovna page.
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { fetchFactoryItems } from '@/lib/api'
import { errorText, shortSha } from '@/lib/format'
import CollapsibleSection from '@/components/ui/CollapsibleSection.vue'
import RosterEditor from './RosterEditor.vue'

const props = defineProps<{ repoId: string; disabled?: boolean }>()
const emit = defineEmits<{ busy: [value: boolean]; success: [] }>()
const open = defineModel<boolean>('open', { default: true })
const library = ref<string | null>(null)
const libraryName = ref<string | null>(null)
const roster = ref<InstanceType<typeof RosterEditor> | null>(null)
const error = ref('')
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
    if (mine === generation) error.value = errorText(e)
  }
}

/** Where an agent without its own copy comes from: the library by name and short commit, or the seed. */
const inheritText = computed(() => library.value
  ? `Agent bez vlastní kopie v .factory/ se dědí z knihovny „${libraryName.value ?? 'knihovna'}“ (${shortSha(library.value)}).`
  : 'Agent bez vlastní kopie v .factory/ se dědí z vestavěné výchozí sady.')

async function reload() {
  await Promise.all([load(), roster.value?.reload()])
}

onMounted(load)
onBeforeUnmount(() => { ++generation; emit('busy', false) })
defineExpose({ reload })
</script>

<template>
  <CollapsibleSection v-model:open="open" heading="Nastavení agentů" class="items" data-test="repo-items">
    <p class="hint" data-test="items-inherit">{{ inheritText }}</p>
    <p v-if="error" role="alert" class="error" data-test="item-error">{{ error }}</p>
    <RosterEditor ref="roster" :repo-id="repoId" :disabled="disabled" @busy="emit('busy', $event)" @saved="emit('success')" />
  </CollapsibleSection>
</template>

<style scoped>
.items { margin-top: 28px; }
.hint { margin: 0 0 8px; color: var(--dim); }
.error { color: var(--red); }
</style>
