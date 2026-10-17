<script setup lang="ts">
// The Nastavení panel of a project or step (`factory backlog edit`): the title and the keys
// of its `index.md`, each with its own value or the inherited one and its origin. Inheriting
// removes the own value. The description of `index.md` is shown read-only. Auto continue and
// the return of the quota chain are three-way switches (Zděděno / Zapnuto / Vypnuto): an unset
// value stays inherited, never off. A project also sets its harness and the quota chain
// (`quota_switch`): a switch and the backup harnesses in order, each at most once.
import { computed, reactive, ref } from 'vue'
import {
  CONTAINER_KEYS,
  HARNESS_KEYS,
  INHERIT_LABEL,
  SETTING_LABELS,
  levelNoun,
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
}

const keys = computed<ContainerKey[]>(() => {
  const allowed = props.editableKeys?.length ? props.editableKeys : CONTAINER_KEYS
  return CONTAINER_KEYS.filter((k) => allowed.includes(k) && (props.container.parent === null || !HARNESS_KEYS.includes(k)))
})

/** Keys edited with the three-way switch instead of an inherit checkbox. */
const FLAG_ROWS: readonly ContainerKey[] = ['auto_continue', 'quota_switch_back']
const isFlag = (key: ContainerKey) => FLAG_ROWS.includes(key)

const own = props.container.own ?? {}
const effective = props.container.effective ?? {}

function hasOwn(key: ContainerKey): boolean {
  return Object.prototype.hasOwnProperty.call(own, key) && own[key] !== null
}

function toText(key: ContainerKey, value: unknown): string {
  if (isFlag(key)) return value === true ? 'on' : value === false ? 'off' : 'inherit'
  if (value === null || value === undefined) return ''
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
        text: isFlag(key)
          ? toText(key, hasOwn(key) ? own[key] : null)
          : toText(key, hasOwn(key) ? own[key] : effective[key]?.value),
      },
    ]),
  ) as Record<ContainerKey, Row>,
)

function parse(key: ContainerKey, text: string): unknown {
  if (isFlag(key)) return text === 'on'
  if (key === 'writes' || key === 'quota_switch') return splitLines(text)
  return text.trim()
}

function same(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

/** A three-way switch: Zděděno sets `inherit`, a value sets an own one. */
function setFlag(key: ContainerKey, value: string) {
  rows[key].text = value
  rows[key].inherit = value === 'inherit'
}

// ── the quota chain (`quota_switch`): on/off and the backup harnesses in order ──
const chain = computed(() => splitLines(rows.quota_switch.text))
const chainOn = ref(chain.value.length > 0)

function setChain(names: string[]) {
  rows.quota_switch.text = names.join('\n')
}
function setChainOn(on: boolean) {
  chainOn.value = on
  if (!on) setChain([])
}
function moveChain(index: number, by: number) {
  const names = [...chain.value]
  const to = index + by
  if (to < 0 || to >= names.length) return
  ;[names[index], names[to]] = [names[to]!, names[index]!]
  setChain(names)
}
function removeChain(index: number) {
  setChain(chain.value.filter((_, i) => i !== index))
}
function addChain(name: string) {
  if (name && !chain.value.includes(name)) setChain([...chain.value, name])
}

/** The project's own harness: it is the start of the chain, never a backup. */
const projectHarness = computed(() => {
  if (!rows.harness.inherit && rows.harness.text) return rows.harness.text
  const value = effective.harness?.value
  return typeof value === 'string' ? value : ''
})
const chainOptions = computed<SelectOption[]>(() =>
  harnessOptions.value.filter((o) => o.value && !chain.value.includes(o.value) && o.value !== projectHarness.value),
)
/** The switch is on with no harness chosen: nothing to save yet. */
const chainIncomplete = computed(
  () => keys.value.includes('quota_switch') && !rows.quota_switch.inherit && chainOn.value && chain.value.length === 0,
)

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
    if (!hasOwn(key) || !same(value, own[key])) {
      ;(out as Record<string, unknown>)[key] = value
    }
  }
  if (clear.length) out.clear = clear
  return out
})

const dirty = computed(() => Object.keys(input.value).length > 0)
const canSave = computed(() => dirty.value && !props.busy && !chainIncomplete.value)

function workflowOptions(): SelectOption[] {
  const names = [...props.workflows]
  const current = rows.workflow.text
  if (current && !names.includes(current)) names.unshift(current)
  return names.map((w) => ({ value: w, label: w }))
}

function flagOptions(key: ContainerKey): SelectOption[] {
  const inherited = effective[key]?.origin?.source === 'own' ? null : effective[key]?.value
  const suffix = typeof inherited === 'boolean' ? ` (${inherited ? 'zapnuto' : 'vypnuto'})` : ''
  return [
    { value: 'inherit', label: `${INHERIT_LABEL}${suffix}` },
    { value: 'on', label: 'Zapnuto' },
    { value: 'off', label: 'Vypnuto' },
  ]
}

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
              <span class="value mono">{{ settingText(effective[key]?.value, key) }}</span>
              <span class="origin own" data-test="origin">vlastní</span>
            </template>
            <template v-else>
              <span class="value mono dim">{{ settingText(effective[key]?.value, key) }}</span>
              <span class="origin faint" data-test="origin">
                zděděno · {{ originText(effective[key]?.origin) }}
              </span>
            </template>
          </td>
          <td>
            <input
              v-if="!isFlag(key)"
              v-model="rows[key].inherit"
              type="checkbox"
              :data-test="`inherit-${key}`"
              :aria-label="`Zdědit ${SETTING_LABELS[key] ?? key}`"
            />
          </td>
          <td>
            <SelectMenu
              v-if="isFlag(key)"
              :model-value="rows[key].text"
              :data-test="`edit-${key}`"
              :label="SETTING_LABELS[key] ?? key"
              :options="flagOptions(key)"
              @update:model-value="(value: string) => setFlag(key, value)"
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
              <div v-else-if="key === 'quota_switch'" class="chain" :data-test="`edit-${key}`">
                <label class="chain-toggle">
                  <input
                    type="checkbox"
                    data-test="quota-switch-on"
                    :checked="chainOn"
                    @change="setChainOn(($event.target as HTMLInputElement).checked)"
                  />
                  Zapnuto
                </label>
                <template v-if="chainOn">
                  <ol class="chain-list">
                    <li v-for="(name, index) in chain" :key="name" data-test="quota-chain-item" :data-harness="name">
                      <span class="mono">{{ name }}</span>
                      <button type="button" data-test="chain-up" :disabled="index === 0" :aria-label="`${name} výš`" @click="moveChain(index, -1)">↑</button>
                      <button type="button" data-test="chain-down" :disabled="index === chain.length - 1" :aria-label="`${name} níž`" @click="moveChain(index, 1)">↓</button>
                      <button type="button" data-test="chain-remove" :aria-label="`Odebrat ${name}`" @click="removeChain(index)">✕</button>
                    </li>
                  </ol>
                  <SelectMenu
                    v-if="chainOptions.length"
                    model-value=""
                    data-test="chain-add"
                    label="Přidat záložní harness"
                    placeholder="přidat harness"
                    :options="chainOptions"
                    @update:model-value="addChain"
                  />
                  <span v-if="!chain.length" class="hint warn" data-test="chain-hint">vyber aspoň jeden harness</span>
                </template>
              </div>
              <textarea
                v-else-if="key === 'writes'"
                v-model="rows[key].text"
                :data-test="`edit-${key}`"
                :placeholder="HINTS[key]"
                rows="2"
              />
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

.hint.warn {
  color: var(--amber);
}

.chain {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.chain-list {
  margin: 0;
  padding-left: 20px;
}

.chain-list li {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 4px;
}

.chain-list li button {
  padding: 2px 8px;
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
