<script setup lang="ts">
import { errorText } from '../lib/format'
// #/repos/add: pick a folder (typed path with suggestions, the folder browser or the system
// dialog), inspect it and add it from its card. An acknowledged legacy sssf installation
// is removed and committed before the fresh factory installation.
import { onMounted, ref } from 'vue'
import { FolderOpen, Search } from 'lucide-vue-next'
import { ApiError, addRepo, fetchDirs, fetchPickStatus, inspectRepo, pickFolder, type InspectResult } from '@/lib/api'
import { USAGE_ERROR_TEXT, pickErrorText } from '@/lib/addRepo'
import { OVERVIEW_HREF, repoHref } from '@/lib/router'
import { pendingInstall as pending, installBusy as operationBusy, installCancelling as cancelling, installCancelError, installRegistering, cancelPendingInstall } from '@/lib/factory'
import OnboardingPanel from '@/components/factory/OnboardingPanel.vue'
import FactoryOperation from '@/components/factory/FactoryOperation.vue'
import BackLink from '@/components/ui/BackLink.vue'
import FolderBrowser from '@/components/repos/FolderBrowser.vue'
import InspectCard from '@/components/repos/InspectCard.vue'
import PathField from '@/components/repos/PathField.vue'
import Spinner from '@/components/ui/Spinner.vue'

const emit = defineEmits<{ added: [id: string] }>()

const pendingAction = ref<'init' | 'onboard'>('init')
async function onboard(root: string) { pendingAction.value = 'onboard'; await install(root) }
async function startInstall(root: string, removeSssf = false) { pendingAction.value = 'init'; await install(root, removeSssf) }
async function install(root: string, removeSssf = false) {
  if(installRegistering.value) return
  installRegistering.value = true
  inspecting.value = true
  inspectError.value = null
  try { const answer = await addRepo(root, removeSssf); pending.value = { id: answer.repo.id, created: answer.created } }
  catch(e) { inspectError.value = errorText(e) }
  finally { inspecting.value = false; installRegistering.value = false }
}
async function cancelInstall() { await cancelPendingInstall() }
/** The repo just added (and maybe installed): the page stays and says what next. */
const done = ref<{ id: string; name: string; href: string; installed: boolean } | null>(null)
function repoName(): string {
  const root = (result.value?.root ?? result.value?.path ?? '').replace(/[\\/]+$/, '')
  return root.split(/[\\/]/).pop() || root
}
function installed() {
  if(!pending.value) return
  const id = pending.value.id
  pending.value.created = false
  pending.value = null
  // A fresh install opens the Factory tab: it lists the next steps (roster, config commit, project).
  done.value = { id, name: repoName() || id, href: repoHref(id, 'factory'), installed: true }
  emit('added', id)
}
function added(id: string, name: string) {
  const ready = result.value?.factory?.state === 'onboarded'
  done.value = { id, name, href: repoHref(id, ready ? 'backlog' : 'factory'), installed: false }
  emit('added', id)
}
function addAnother() {
  done.value = null
  result.value = null
  inspectError.value = null
  path.value = '~/'
}
const path = ref('~/')
const home = ref<string | null>(null)
const pickAvailable = ref(false)
const picking = ref(false)
const pickError = ref<string | null>(null)
const browsing = ref(false)
const inspecting = ref(false)
const result = ref<InspectResult | null>(null)
const inspectError = ref<string | null>(null)
let generation = 0

async function inspect(value: string = path.value): Promise<void> {
  const raw = value.trim()
  if (!raw) return
  const mine = ++generation
  inspecting.value = true
  result.value = null
  inspectError.value = null
  try {
    const data = await inspectRepo(raw)
    if (mine === generation) result.value = data
  } catch (err) {
    if (mine !== generation) return
    if (err instanceof ApiError && err.code === 'usage_error') inspectError.value = USAGE_ERROR_TEXT
    else inspectError.value = errorText(err)
  } finally {
    if (mine === generation) inspecting.value = false
  }
}

function useFolder(folder: string) {
  path.value = folder
  void inspect(folder)
}

function chooseFromBrowser(folder: string) {
  browsing.value = false
  useFolder(folder)
}

async function pick() {
  picking.value = true
  pickError.value = null
  try {
    const answer = await pickFolder()
    if (answer.path) useFolder(answer.path)
  } catch (err) {
    pickError.value =
      err instanceof ApiError ? pickErrorText(err.code, err.message) : errorText(err)
  } finally {
    picking.value = false
  }
}

onMounted(async () => {
  const [dirs, pickStatus] = await Promise.allSettled([fetchDirs(), fetchPickStatus()])
  if (dirs.status === 'fulfilled') home.value = dirs.value.path
  pickAvailable.value = pickStatus.status === 'fulfilled' && pickStatus.value.available === true
})
</script>

<template>
  <section class="add-view" data-test="repos-add">
    <template v-if="done">
      <BackLink :href="OVERVIEW_HREF" label="Přehled" />
      <article class="done-card" data-test="repo-added">
        <h1>Repozitář {{ done.name }} přidán</h1>
        <p v-if="done.installed" class="note">Factory je nainstalovaná. V záložce Factory najdeš další kroky.</p>
        <div class="done-actions">
          <a :href="done.href" class="btn ok" data-test="repo-added-open">Otevřít repo</a>
          <button type="button" class="btn" data-test="repo-added-another" @click="addAnother">Přidat další repozitář</button>
        </div>
      </article>
    </template>
    <template v-else-if="!pending">
    <BackLink :href="OVERVIEW_HREF" label="Přehled" />
    <h1>Přidat repozitář</h1>
    <h2 class="step"><span class="step-no">1</span> Složka</h2>
    <div class="folder-row">
      <PathField v-model="path" :home="home" @submit="inspect()" />
      <button type="button" class="btn ok" :disabled="inspecting" data-test="add-inspect" @click="inspect()">
        <Spinner v-if="inspecting" /><Search v-else :size="14" aria-hidden="true" /> Zkontrolovat
      </button>
    </div>
    <div class="folder-actions">
      <button type="button" class="btn" data-test="add-browse" @click="browsing = true">
        <FolderOpen :size="14" aria-hidden="true" /> Procházet…
      </button>
      <button v-if="pickAvailable" type="button" class="btn" :disabled="picking" data-test="add-pick" @click="pick">
        <Spinner v-if="picking" /> Vybrat ve Finderu…
      </button>
    </div>
    <p v-if="pickError" class="error" data-test="pick-error">{{ pickError }}</p>
    <p v-if="inspectError" class="error" data-test="inspect-error">{{ inspectError }}</p>
    <InspectCard
      v-if="result"
      :key="result.path"
      :inspect="result"
      @added="added"
      @reinspect="useFolder"
      @install="startInstall"
      @onboard="onboard"
    />
    <FolderBrowser :open="browsing" @choose="chooseFromBrowser" @close="browsing = false" />
    </template>
    <template v-else>
      <h1>Přidat repozitář — {{ pendingAction === 'init' ? 'instalace factory' : 'onboarding' }}</h1>
      <button type="button" class="btn" :disabled="operationBusy || cancelling" data-test="cancel-install" @click="cancelInstall">Zrušit</button>
      <p v-if="installCancelError || inspectError" class="error">{{ installCancelError || inspectError }}</p>
      <OnboardingPanel v-if="pendingAction === 'onboard'" :repo-id="pending.id" action="onboard" @busy="operationBusy = $event" @success="installed" />
      <FactoryOperation v-else action="init" :repo-id="pending.id" @busy="operationBusy = $event" @success="installed" />
    </template>
  </section>
</template>

<style scoped>
.add-view {
  padding: 28px;
  max-width: 1000px;
  margin: 0 auto;
}

h1 {
  margin: 0 0 18px;
  font-size: 24px;
  font-weight: 700;
  letter-spacing: 0.02em;
}

.step {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  color: var(--dim);
  font-size: 16px;
  font-weight: 600;
}

.step-no {
  display: inline-grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--panel-3);
  color: var(--text);
  font-size: 13px;
}

.folder-row {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.folder-actions {
  display: flex;
  gap: 10px;
  margin-top: 10px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  white-space: nowrap;
  cursor: pointer;
}

.btn:disabled {
  cursor: default;
  opacity: 0.7;
}

.btn.ok {
  border-color: rgba(74, 222, 128, 0.55);
  color: var(--green);
  font-weight: 700;
}

.done-card {
  padding: 18px 20px;
  border: 1px solid rgba(74, 222, 128, 0.45);
  border-radius: 12px;
  background: var(--surface);
}

.done-actions {
  display: flex;
  gap: 10px;
  margin-top: 14px;
}

.done-actions a.btn {
  text-decoration: none;
}

.note {
  margin: 0;
  color: var(--dim);
}

.error {
  margin: 12px 0 0;
  color: var(--red);
}
</style>
