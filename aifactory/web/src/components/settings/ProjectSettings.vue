<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { editContainer, originText } from '@/lib/backlog'
import { ApiError } from '@/lib/api'
import { errorText } from '@/lib/format'
import type { SettingsData } from '@/lib/settings'
import SelectMenu from '@/components/ui/SelectMenu.vue'

const props = defineProps<{ settings: SettingsData }>()
const emit = defineEmits<{ saved: [] }>()
const keys = ['specs_dir', 'docs_dir', 'workdir'] as const
const labels = { specs_dir: 'Adresář specs', docs_dir: 'Adresář dokumentace', workdir: 'Pracovní adresář agentů' }
const selected = ref(props.settings.projects?.[0]?.id ?? '')
const projectOptions = computed(() => (props.settings.projects ?? []).map(p => ({
  value: p.id, label: `${p.id} — ${p.title}`,
})))
const project = computed(() => props.settings.projects?.find(p => p.id === selected.value))
const values = ref({ specs_dir: '', docs_dir: '', workdir: '' })
const busy = ref(false)
const error = ref('')
watch(project, p => {
  for (const key of keys) values.value[key] = String(p?.own[key] ?? '')
  error.value = ''
}, { immediate: true })
const changed = computed(() => keys.some(key => values.value[key] !== String(project.value?.own[key] ?? '')))

async function save(): Promise<void> {
  if (!project.value || busy.value || !changed.value) return
  busy.value = true
  error.value = ''
  try {
    const input: Record<string, string | null> = {}
    for (const key of keys) {
      if (values.value[key] !== String(project.value.own[key] ?? '')) input[key] = values.value[key].trim() || null
    }
    await editContainer(project.value.id, input)
    emit('saved')
  } catch (err) {
    error.value = err instanceof ApiError ? err.issues.map(i => i.message).join('; ') || err.message : errorText(err)
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="project-settings" data-test="project-settings" @submit.prevent="save">
    <fieldset :disabled="busy">
      <legend>Sdílené nastavení projektu (index.md, commituje se)</legend>
      <label>
        Projekt repozitáře
        <SelectMenu
          v-model="selected"
          data-test="project-select"
          label="Projekt repozitáře"
          :options="projectOptions"
          :disabled="busy || !projectOptions.length"
        />
      </label>
      <p v-if="!project">Repozitář nemá žádný projekt backlogu.</p>
      <template v-else>
        <p><code>{{ project.index_path }}</code></p>
        <label v-for="key in keys" :key="key">
          {{ labels[key] }}
          <input v-model="values[key]" :data-test="`project-${key}`" :placeholder="settings.shared[key]" type="text" />
          <span class="hint" :data-test="`project-origin-${key}`">
            Účinná hodnota: {{ values[key].trim() || settings.shared[key] }} ·
            {{ values[key].trim() ? `Vlastní: ${project.index_path}` : `Zděděná: .factory/config.yaml (${key})` }}.
            Uložený původ: {{ originText(project.effective[key]?.origin) }}
          </span>
          <button type="button" :data-test="`inherit-${key}`" @click="values[key] = ''">Obnovit dědění</button>
        </label>
        <p class="hint">Cesty jsou relativní ke kořeni repozitáře. Prázdná hodnota odstraní přetížení. Běhy čtou sdílené změny až z base commitu.</p>
        <button type="submit" :disabled="!changed || busy" data-test="project-save">Uložit projekt</button>
      </template>
      <p v-if="error" class="field-error" role="alert">{{ error }}</p>
    </fieldset>
  </form>
</template>

<style scoped>
.project-settings { max-width: 760px; margin-top: 16px; }
fieldset { display: flex; flex-direction: column; gap: 12px; padding: 16px 18px; border: 1px solid var(--border); border-radius: 10px; background: var(--panel-2); }
legend { font-weight: 600; }
label { display: flex; flex-direction: column; gap: 4px; color: var(--dim); }
input, button { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel); color: var(--text); font: inherit; }
button { align-self: flex-start; cursor: pointer; }
button:disabled { opacity: .5; cursor: default; }
.hint { color: var(--faint); font-size: 13px; }
.field-error { color: var(--red); }
</style>
