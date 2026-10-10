<script setup lang="ts">
import { errorText, shortSha } from '../lib/format'
// #/repos/add: pick a folder (typed path with suggestions, the folder browser or the system
// dialog), inspect it and add it from its card. Adding registers the repo and commits
// factory from the library on its base in one go.
import { onMounted, ref } from 'vue'
import { FolderOpen, Search } from 'lucide-vue-next'
import { ApiError, fetchDirs, fetchPickStatus, inspectRepo, pickFolder, type AddRepoResult, type InspectResult, type RepoInstall } from '@/lib/api'
import { USAGE_ERROR_TEXT, pickErrorText } from '@/lib/addRepo'
import { OVERVIEW_HREF, repoHref } from '@/lib/router'
import BackLink from '@/components/ui/BackLink.vue'
import FolderBrowser from '@/components/repos/FolderBrowser.vue'
import InspectCard from '@/components/repos/InspectCard.vue'
import PathField from '@/components/repos/PathField.vue'
import Spinner from '@/components/ui/Spinner.vue'

const emit = defineEmits<{ added: [id: string] }>()

/** The repo just added (or synced): the page stays and says what the install committed. */
const done = ref<{ id: string; name: string; href: string; synced: boolean; install: RepoInstall } | null>(null)
function added(answer: AddRepoResult) {
  const synced = result.value?.registered != null
  const { repo } = answer
  const install = answer.install ?? { committed: false, commit: null, pushed: false, files: [] }
  done.value = { id: repo.id, name: repo.name || repo.id, href: repoHref(repo.id, 'factory'), synced, install }
  emit('added', repo.id)
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
        <h1>Repozitář {{ done.name }} {{ done.synced ? 'synchronizován' : 'přidán' }}</h1>
        <p class="note" data-test="repo-added-install">
          <template v-if="done.install.committed">Factory z knihovny commitnuta {{ shortSha(done.install.commit) }} ({{ done.install.files.length }} {{ done.install.files.length === 1 ? 'soubor' : (done.install.files.length < 5 ? 'soubory' : 'souborů') }}), {{ done.install.pushed ? 'pushnuto' : 'bez pushe' }}.</template>
          <template v-else>Factory odpovídá knihovně, beze změny.</template>
          V záložce Factory najdeš další kroky.
        </p>
        <div class="done-actions">
          <a :href="done.href" class="btn ok" data-test="repo-added-open">Otevřít repo</a>
          <button type="button" class="btn" data-test="repo-added-another" @click="addAnother">Přidat další repozitář</button>
        </div>
      </article>
    </template>
    <template v-else>
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
    />
    <FolderBrowser :open="browsing" @choose="chooseFromBrowser" @close="browsing = false" />
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
