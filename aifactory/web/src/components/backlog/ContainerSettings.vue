<script setup lang="ts">
// The Nastavení panel of a project or step (`factory backlog edit`): the title and the keys
// of its `index.md`, each with its own value or the inherited one and its origin. Inheriting
// removes the own value. The description of `index.md` is shown read-only. Auto continue is
// one three-way switch (Zděděno / Zapnuto / Vypnuto): an unset value stays inherited, never off.
import { computed, reactive, ref } from 'vue'
import {
  CONTAINER_KEYS,
  INHERIT_LABEL,
  SETTING_LABELS,
  TEST_FIELD_HINT,
  formatTestField,
  levelNoun,
  parseTestField,
  originText,
  settingText,
  splitLines,
  type ContainerDetail,
  type ContainerKey,
  type EditContainerInput,
  type WriteError,
} from '@/lib/backlog'
import type { SelectOption } from '@/lib/select'
import MarkdownView from '@/components/ui/MarkdownView.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'
import IssueList from './IssueList.vue'
import { useHarnessChoices } from '@/lib/machineHarnesses'

const props = defineProps<{
  container: ContainerDetail
  workflows: string[]
  /** Keys the API lets the panel edit; defaults to `CONTAINER_KEYS`. */
  editableKeys?: string[]
  busy: boolean
  /** The save is running (spinner in Uložit). */
  pending?: boolean
  error: WriteError | null
}>()

const emit = defineEmits<{ save: [input: EditContainerInput] }>()
const { harnessOptions, modelOptions } = useHarnessChoices()

const HINTS: Partial<Record<ContainerKey, string>> = {
  writes: 'jedna cesta na řádek',
  test: 'např. just check',
}

const keys = computed<ContainerKey[]>(() => {
  const allowed = props.editableKeys?.length ? props.editableKeys : CONTAINER_KEYS
  return CONTAINER_KEYS.filter((k) => allowed.includes(k) && (props.container.parent === null || !['harness', 'model', 'thinking'].includes(k)))
})

const own = props.container.own ?? {}
const effective = props.container.effective ?? {}

function hasOwn(key: ContainerKey): boolean {
  return Object.prototype.hasOwnProperty.call(own, key) && own[key] !== null
}

function toText(key: ContainerKey, value: unknown): string {
  if (key === 'auto_continue') return value === true ? 'on' : value === false ? 'off' : 'inherit'
  if (value === null || value === undefined) return ''
  if (key === 'test') return formatTestField(value)
  if (Array.isArray(value)) return value.map(String).join('\n')
  return String(value)
}

interface Row {
  inherit: boolean
  text: string
}

const initialTitle = props.container.title ?? ''
const title = ref(initialTitle)
const rows = reactive(
  Object.fromEntries(
    CONTAINER_KEYS.map((key) => [
      key,
      {
        inherit: !hasOwn(key),
        // switching an inherited key to own starts from the inherited value; the auto continue
        // switch starts at Zděděno
        text: key === 'auto_continue'
          ? toText(key, hasOwn(key) ? own[key] : null)
          : toText(key, hasOwn(key) ? own[key] : effective[key]?.value),
      },
    ]),
  ) as Record<ContainerKey, Row>,
)

function parse(key: ContainerKey, text: string): unknown {
  if (key === 'auto_continue') return text === 'on'
  if (key === 'writes') return splitLines(text)
  if (key === 'test') return parseTestField(text) ?? []
  return text.trim()
}

function same(key: ContainerKey, a: unknown, b: unknown): boolean {
  // a test command in another form (string or argv) is the same command
  if (key === 'test') return JSON.stringify(parseTestField(formatTestField(a))) === JSON.stringify(parseTestField(formatTestField(b)))
  return JSON.stringify(a) === JSON.stringify(b)
}

/** The auto continue switch: Zděděno sets `inherit`, a value sets an own one. */
function setAutoContinue(value: string) {
  rows.auto_continue.text = value
  rows.auto_continue.inherit = value === 'inherit'
}

function setHarness(value: string) {
  rows.harness.text = value
  rows.harness.inherit = !value
  rows.model.text = ''
  rows.model.inherit = true
}
function setModel(value: string) {
  rows.model.text = value
  rows.model.inherit = !value
}

const input = computed<EditContainerInput>(() => {
  const out: EditContainerInput = {}
  const clear: ContainerKey[] = []
  if (title.value.trim() !== initialTitle) out.title = title.value.trim()
  for (const key of keys.value) {
    const row = rows[key]
    if (row.inherit) {
      if (hasOwn(key)) clear.push(key)
      continue
    }
    const value = parse(key, row.text)
    if (!hasOwn(key) || !same(key, value, own[key])) {
      ;(out as Record<string, unknown>)[key] = value
    }
  }
  if (clear.length) out.clear = clear
  return out
})

const dirty = computed(() => Object.keys(input.value).length > 0)
const canSave = computed(() => dirty.value && !props.busy)

function workflowOptions(): SelectOption[] {
  const names = [...props.workflows]
  const current = rows.workflow.text
  if (current && !names.includes(current)) names.unshift(current)
  return names.map((w) => ({ value: w, label: w }))
}

const flagOptions = computed<SelectOption[]>(() => {
  const inherited = effective.auto_continue?.origin?.source === 'own' ? null : effective.auto_continue?.value
  const suffix = typeof inherited === 'boolean' ? ` (${inherited ? 'zapnuto' : 'vypnuto'})` : ''
  return [
    { value: 'inherit', label: `${INHERIT_LABEL}${suffix}` },
    { value: 'on', label: 'Zapnuto' },
    { value: 'off', label: 'Vypnuto' },
  ]
})

const levelGen = computed(() => levelNoun(props.container.level, 'gen'))

function onSave() {
  if (canSave.value) emit('save', input.value)
}
</script>

<template>
  <form class="container-settings" data-test="container-settings" @submit.prevent="onSave">
    <h3>Nastavení</h3>
    <p class="note" data-test="commit-note">
      Změny se zapíší do <code>{{ container.index_path ?? container.path }}</code> v pracovním
      stromu. Běhy je použijí až po commitu backlogu do base.
    </p>

    <label class="title-row">
      Název
      <input v-model="title" data-test="settings-title" type="text" required />
    </label>

    <table class="settings">
      <thead>
        <tr>
          <th>Klíč</th>
          <th>Platná hodnota</th>
          <th>Zdědit</th>
          <th>Vlastní hodnota</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="key in keys"
          :key="key"
          :data-setting="key"
          :data-source="effective[key]?.origin?.source ?? 'none'"
        >
          <th scope="row">
            <span class="setting-label" data-test="setting-label">{{ SETTING_LABELS[key] ?? key }}</span>
            <code class="setting-key">{{ key }}</code>
          </th>
          <td :data-test="`value-${key}`">
            <template v-if="effective[key]?.origin?.source === 'own'">
              <span class="value mono">{{ settingText(effective[key]?.value) }}</span>
              <span class="origin own" data-test="origin">vlastní</span>
            </template>
            <template v-else>
              <span class="value mono dim">{{ settingText(effective[key]?.value) }}</span>
              <span class="origin faint" data-test="origin">
                zděděno · {{ originText(effective[key]?.origin) }}
              </span>
            </template>
          </td>
          <td>
            <input
              v-if="key !== 'auto_continue'"
              v-model="rows[key].inherit"
              type="checkbox"
              :data-test="`inherit-${key}`"
              :aria-label="`Zdědit ${SETTING_LABELS[key] ?? key}`"
            />
          </td>
          <td>
            <SelectMenu
              v-if="key === 'auto_continue'"
              :model-value="rows[key].text"
              :data-test="`edit-${key}`"
              :label="SETTING_LABELS[key] ?? key"
              :options="flagOptions"
              @update:model-value="setAutoContinue"
            />
            <template v-else-if="!rows[key].inherit">
              <SelectMenu v-if="key === 'harness'" :model-value="rows[key].text" :options="harnessOptions" label="Harness projektu" :data-test="`edit-${key}`" @update:model-value="setHarness" />
              <SelectMenu v-else-if="key === 'model'" :model-value="rows[key].text" :options="modelOptions(rows.harness.inherit ? '' : rows.harness.text)" label="Model projektu" :data-test="`edit-${key}`" @update:model-value="setModel" />
              <SelectMenu
                v-else-if="key === 'workflow'"
                v-model="rows[key].text"
                :data-test="`edit-${key}`"
                label="Workflow"
                placeholder="vyber workflow"
                :options="workflowOptions()"
              />
              <textarea
                v-else-if="key === 'writes'"
                v-model="rows[key].text"
                :data-test="`edit-${key}`"
                :placeholder="HINTS[key]"
                rows="2"
              />
              <template v-else-if="key === 'test'">
                <input v-model="rows[key].text" :data-test="`edit-${key}`" type="text" :placeholder="HINTS[key]" />
                <span class="hint faint" data-test="test-hint">{{ TEST_FIELD_HINT }}</span>
              </template>
              <input v-else v-model="rows[key].text" :data-test="`edit-${key}`" type="text" />
            </template>
            <span v-else class="faint">dědí se</span>
          </td>
        </tr>
      </tbody>
    </table>

    <div class="actions">
      <button
        type="submit"
        class="primary"
        data-test="settings-save"
        :disabled="!canSave"
        :aria-busy="pending || undefined"
      >
        <Spinner v-if="pending" />
        Uložit
      </button>
    </div>

    <IssueList v-if="error" :message="error.message" :issues="error.issues" />

    <section class="description">
      <h4>Popis {{ levelGen }}</h4>
      <MarkdownView :source="container.body ?? ''" data-test="container-body" empty="Bez popisu." />
    </section>
  </form>
</template>

<style scoped>
.container-settings {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 18px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

h3,
h4 {
  margin: 0;
}

h3 {
  font-size: 18px;
}

h4 {
  font-size: 15px;
  margin-bottom: 6px;
}

.note {
  margin: 0;
  padding: 8px 12px;
  border: 1px solid rgba(232, 182, 74, 0.45);
  border-radius: 8px;
  background: rgba(232, 182, 74, 0.08);
  color: var(--amber);
}

.title-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 520px;
  color: var(--dim);
}

table.settings {
  border-collapse: collapse;
  width: 100%;
}

table.settings th,
table.settings td {
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
  text-align: left;
  vertical-align: top;
}

thead th {
  color: var(--faint);
  font-weight: 500;
  font-size: 13px;
}

.value {
  margin-right: 8px;
}

.origin {
  font-size: 13px;
}

.origin.own {
  color: var(--blue);
}

.mono {
  font-family: var(--mono);
  font-size: 14px;
}

.setting-label {
  display: block;
  font-weight: 500;
}

.setting-key {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--faint);
}

.hint {
  display: block;
  margin-top: 4px;
  font-size: 13px;
}

input[type='text'],
textarea {
  width: 100%;
  box-sizing: border-box;
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
