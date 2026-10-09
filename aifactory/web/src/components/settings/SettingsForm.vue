<script setup lang="ts">
// The settings form: shared .factory/config.yaml and local .factory/local.yaml.
import { computed, ref } from 'vue'
import {
  formValues,
  isEmptyInput,
  settingsDiff,
  type SettingsData,
  type SettingsFormValues,
  type SettingsSaveInput,
} from '@/lib/settings'
import type { SelectOption } from '@/lib/select'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'

const props = defineProps<{
  settings: SettingsData
  busy: boolean
  errors: Record<string, string[]>
}>()

const emit = defineEmits<{
  submit: [input: SettingsSaveInput]
  reset: []
}>()

type TextField = 'workdir' | 'backlog_dir' | 'specs_dir' | 'docs_dir' | 'worktrees_dir' | 'base'

const PATH_FIELDS: { name: TextField; label: string; hint: string }[] = [
  { name: 'workdir', label: 'Pracovní adresář agentů', hint: '. = kořen repa, nebo podadresář' },
  { name: 'backlog_dir', label: 'Adresář backlogu', hint: 'relativně ke kořeni repa' },
  { name: 'specs_dir', label: 'Adresář specs', hint: 'relativně ke kořeni repa' },
  { name: 'docs_dir', label: 'Adresář dokumentace', hint: 'relativně ke kořeni repa' },
  { name: 'worktrees_dir', label: 'Adresář worktree', hint: 'relativně ke kořeni repa' },
  { name: 'base', label: 'Base větev', hint: 'větev, ze které běhy čtou konfiguraci a backlog' },
]

const initial = ref<SettingsFormValues>(formValues(props.settings))
const values = ref<SettingsFormValues>({ ...initial.value })

const diff = computed(() => settingsDiff(initial.value, values.value))
const canSave = computed(() => !props.busy && !isEmptyInput(diff.value))
const general = computed(() => props.errors[''] ?? [])
const fileIssues = computed(() => [...props.settings.shared_issues, ...props.settings.local_issues])

// A value the file holds but the server does not offer stays visible as its own option.
function choiceOptions(choices: string[], current: string): SelectOption[] {
  const values = choices.includes(current) ? choices : [current, ...choices]
  return values.map((v) => ({ value: v, label: v }))
}

const gitProviderOptions = computed(() =>
  choiceOptions(props.settings.options.git_provider, values.value.git_provider),
)
const mergeStrategyOptions = computed(() =>
  choiceOptions(props.settings.options.merge_strategy, values.value.merge_strategy),
)

function fieldError(name: string): string[] {
  return props.errors[name] ?? []
}

function invalid(name: string): boolean {
  return fieldError(name).length > 0
}

function onSubmit(): void {
  if (canSave.value) emit('submit', diff.value)
}

function onReset(): void {
  values.value = { ...initial.value }
  emit('reset')
}
</script>

<template>
  <form class="settings-form" data-test="settings-form" @submit.prevent="onSubmit">
    <div v-if="fileIssues.length" class="warning" data-test="file-issues">
      <p>Soubor je teď neplatný:</p>
      <ul>
        <li v-for="(issue, i) in fileIssues" :key="i" class="mono">{{ issue.path }}: {{ issue.message }}</li>
      </ul>
    </div>

    <fieldset>
      <legend>Sdílené nastavení repozitáře (<code>{{ settings.files.shared }}</code>, commituje se)</legend>

      <label v-for="field in PATH_FIELDS" :key="field.name">
        {{ field.label }}
        <input
          v-model="values[field.name]"
          type="text"
          :data-test="field.name"
          :class="{ invalid: invalid(field.name) }"
          :aria-invalid="invalid(field.name) ? 'true' : undefined"
        />
        <span class="hint">{{ field.hint }}</span>
        <span v-for="msg in fieldError(field.name)" :key="msg" class="field-error" :data-test="`error-${field.name}`">{{ msg }}</span>
      </label>

      <label>
        Git provider
        <SelectMenu
          v-model="values.git_provider"
          data-test="git_provider"
          label="Git provider"
          :options="gitProviderOptions"
          :invalid="invalid('git_provider')"
        />
        <span v-if="values.git_provider === 'azure'" class="hint" data-test="azure-hint">
          Sekce <code>azure</code> se tady needituje. Když v souboru chybí, uložení selže.
        </span>
        <span v-for="msg in fieldError('git_provider')" :key="msg" class="field-error" data-test="error-git_provider">{{ msg }}</span>
      </label>

      <label>
        Merge strategie
        <SelectMenu
          v-model="values.merge_strategy"
          data-test="merge_strategy"
          label="Merge strategie"
          :options="mergeStrategyOptions"
          :invalid="invalid('merge_strategy')"
        />
        <span v-for="msg in fieldError('merge_strategy')" :key="msg" class="field-error" data-test="error-merge_strategy">{{ msg }}</span>
      </label>

      <label>
        Výchozí testovací příkaz
        <input
          v-model="values.test_command"
          type="text"
          placeholder="žádný"
          data-test="test_command"
          :class="{ invalid: invalid('test_command') }"
          :aria-invalid="invalid('test_command') ? 'true' : undefined"
        />
        <span v-for="msg in fieldError('test_command')" :key="msg" class="field-error" data-test="error-test_command">{{ msg }}</span>
      </label>

      <label>
        Souběžné běhy auto-continue
        <input
          v-model="values.max_parallel_runs"
          type="text"
          inputmode="numeric"
          data-test="max_parallel_runs"
          :class="{ invalid: invalid('max_parallel_runs') }"
          :aria-invalid="invalid('max_parallel_runs') ? 'true' : undefined"
        />
        <span class="hint">
          Kolik běhů řetěz auto-continue drží naráz (1 = jeden po druhém). Tasky s překrývajícími se
          writes neběží souběžně.
        </span>
        <span v-for="msg in fieldError('max_parallel_runs')" :key="msg" class="field-error" data-test="error-max_parallel_runs">{{ msg }}</span>
      </label>

      <label>
        Chráněné soubory
        <textarea
          v-model="values.protected_files"
          rows="4"
          data-test="protected_files"
          :class="{ invalid: invalid('protected_files') }"
          :aria-invalid="invalid('protected_files') ? 'true' : undefined"
        />
        <span class="hint">jedna cesta na řádek</span>
        <span v-for="msg in fieldError('protected_files')" :key="msg" class="field-error" data-test="error-protected_files">{{ msg }}</span>
      </label>
    </fieldset>

    <fieldset>
      <legend>Lokální necommitované nastavení (<code>{{ settings.files.local }}</code>, mimo git)</legend>

      <label>
        Cesta k trace DB
        <input
          v-model="values.trace_db"
          type="text"
          data-test="trace_db"
          :class="{ invalid: invalid('trace_db') }"
          :aria-invalid="invalid('trace_db') ? 'true' : undefined"
        />
        <span v-for="msg in fieldError('trace_db')" :key="msg" class="field-error" data-test="error-trace_db">{{ msg }}</span>
      </label>
    </fieldset>

    <ul v-if="general.length" class="field-error general" data-test="error-general">
      <li v-for="msg in general" :key="msg">{{ msg }}</li>
    </ul>

    <div class="actions">
      <button
        type="submit"
        class="primary"
        data-test="save"
        :disabled="!canSave"
        :aria-busy="busy || undefined"
      >
        <Spinner v-if="busy" />
        Uložit
      </button>
      <button type="button" data-test="reset" :disabled="busy" @click="onReset">Vrátit</button>
    </div>
  </form>
</template>

<style scoped>
.settings-form {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 760px;
}

fieldset {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 0;
  padding: 16px 18px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

legend {
  padding: 0 6px;
  font-weight: 600;
}

label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  color: var(--dim);
}

input[type='text'],
textarea {
  padding: 6px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
}

textarea {
  font-family: var(--mono);
  font-size: 14px;
}

.invalid {
  border-color: var(--red);
}

.hint {
  font-size: 13px;
  color: var(--faint);
}

.field-error {
  display: block;
  margin: 0;
  color: var(--red);
  font-size: 14px;
}

.field-error.general {
  padding-left: 18px;
}

.warning {
  padding: 8px 12px;
  border: 1px solid rgba(232, 182, 74, 0.45);
  border-radius: 8px;
  background: rgba(232, 182, 74, 0.08);
  color: var(--amber);
}

.warning p {
  margin: 0;
}

.warning li {
  color: var(--text);
}

.actions {
  display: flex;
  gap: 10px;
}

button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
  color: var(--text);
  font: inherit;
  cursor: pointer;
}

button.primary {
  border-color: var(--blue);
  color: var(--blue);
}

button:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
