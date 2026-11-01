<script setup lang="ts">
// The Lekce section of the Factory screen: the lessons `factory learn scan` found in the
// objections that kept coming back in the runs. A proposed lesson shows its rule, where the
// rule belongs, its occurrences with links to the runs, Přijmout (`factory learn accept`: a
// backlog task that writes the rule) and Zamítnout (`factory learn dismiss`). An accepted
// lesson links its task and, once the task's PR is merged, counts the runs with a similar
// objection before and after the merge (grouped by the scan, so a later scan updates it).
// Najít lekce starts the scan in the background; the section polls until it ends. With Ze
// všech rep (on by default) the scan reads the objections of every registered repo and saves
// each lesson in its target repo: a lesson shows the repos its objections come from, each
// objection its repo, and a finished scan links the Lekce section of the repos that got
// lessons. `#/r/<id>/factory/lessons` opens and scrolls to this section.
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Search } from 'lucide-vue-next'
import { ApiError } from '@/lib/api'
import { errorText, fmtTime, plural } from '@/lib/format'
import {
  SOURCE_TEXT,
  acceptLesson,
  dismissLesson,
  fetchLearn,
  lessonsElsewhere,
  startLessonScan,
  targetText,
  type Lesson,
  type LessonComplaint,
  type LessonScan,
} from '@/lib/learn'
import { useNames } from '@/lib/names'
import { currentRepoId, repoHref, runHref, taskHref, useRouteParams } from '@/lib/router'
import CollapsibleSection from '@/components/ui/CollapsibleSection.vue'
import SelectMenu from '@/components/ui/SelectMenu.vue'
import Spinner from '@/components/ui/Spinner.vue'
import Tooltip from '@/components/ui/Tooltip.vue'

const props = withDefaults(defineProps<{ pollMs?: number; disabled?: boolean }>(), { pollMs: 2000, disabled: false })
const open = defineModel<boolean>('open', { default: true })

const lessons = ref<Lesson[]>([])
const scan = ref<LessonScan | null>(null)
const loading = ref(true)
/** The error of Najít lekce, Přijmout or Zamítnout; `loadError` is the one of the list. */
const error = ref<string | null>(null)
const loadError = ref<string | null>(null)
const starting = ref(false)
/** The lesson a request is running for (Přijmout or Zamítnout). */
const acting = ref<string | null>(null)
const notice = ref<string | null>(null)
/** The lesson whose acceptance needs a project chosen by the person, with the choice. */
const projectFor = ref<string | null>(null)
const project = ref('')
/** Ze všech rep: the scan reads the objections of every registered repo. */
const allRepos = ref(true)
const ownRepo = currentRepoId()
const section = ref<InstanceType<typeof CollapsibleSection> | null>(null)

const { names, levels } = useNames()
const projectOptions = computed(() =>
  Object.entries(names.value)
    .filter(([, n]) => n.level === levels.value[0])
    .map(([id, n]) => ({ value: id, label: n.title ? `${id} – ${n.title}` : id }))
    .sort((a, b) => a.value.localeCompare(b.value)),
)

const proposed = computed(() => lessons.value.filter((l) => l.state === 'proposed'))
const accepted = computed(() => lessons.value.filter((l) => l.state === 'accepted'))
const rejected = computed(() => lessons.value.filter((l) => l.state === 'rejected'))
const scanning = computed(() => starting.value || scan.value?.state === 'running')
const busy = computed(() => props.disabled || acting.value !== null)
const elsewhere = computed(() => (scan.value?.state === 'done' ? lessonsElsewhere(scan.value.result) : []))
const elsewhereTotal = computed(() => elsewhere.value.reduce((sum, [, n]) => sum + n, 0))
const scanWarnings = computed(() => (scan.value?.state === 'done' ? (scan.value.result?.warnings ?? []) : []))

/** The Lekce section of another repo: the link switches the repo like the rest of the dashboard. */
function lessonsHref(repo: string): string {
  return repoHref(repo, 'factory', 'lessons')
}

/** A run or task of an objection from another repo opens in that repo. */
function complaintRunHref(c: LessonComplaint): string {
  return c.repo && c.repo !== ownRepo ? repoHref(c.repo, 'runs', c.run_id) : runHref(c.run_id)
}

function complaintTaskHref(c: LessonComplaint): string {
  return c.repo && c.repo !== ownRepo ? repoHref(c.repo, 'backlog', c.task_id) : taskHref(c.task_id)
}

function originTip(lesson: Lesson): string {
  return lesson.origin.length === 1
    ? `Výtky této lekce jsou z běhů repa ${lesson.origin[0]}.`
    : `Výtky této lekce jsou z běhů rep ${lesson.origin.join(', ')}.`
}

function lessonsCount(n: number): string {
  return `${n} ${plural(n, 'lekce', 'lekce', 'lekcí')}`
}

const params = useRouteParams()
watch(
  params,
  async (value) => {
    if (value[0] !== 'lessons') return
    open.value = true
    await nextTick()
    const el = section.value?.$el as HTMLElement | undefined
    el?.scrollIntoView?.({ behavior: 'smooth', block: 'start' })
  },
  { immediate: true },
)

let timer: ReturnType<typeof setTimeout> | undefined
let generation = 0

async function load(): Promise<void> {
  const mine = ++generation
  clearTimeout(timer)
  try {
    const data = await fetchLearn()
    if (mine !== generation) return
    lessons.value = Array.isArray(data?.lessons) ? data.lessons : []
    scan.value = data?.scan ?? null
    loadError.value = null
    if (scan.value?.state === 'running') timer = setTimeout(() => void load(), props.pollMs)
  } catch (e) {
    if (mine === generation) loadError.value = errorText(e)
  } finally {
    if (mine === generation) loading.value = false
  }
}

async function findLessons(): Promise<void> {
  if (scanning.value || busy.value) return
  starting.value = true
  notice.value = null
  error.value = null
  try {
    scan.value = await startLessonScan({ all: allRepos.value })
  } catch (e) {
    error.value = errorText(e)
  } finally {
    starting.value = false
  }
  await load()
}

async function accept(lesson: Lesson, chosen: string | null = null): Promise<void> {
  if (busy.value) return
  acting.value = lesson.id
  notice.value = null
  error.value = null
  try {
    const result = await acceptLesson(lesson.id, chosen)
    projectFor.value = null
    notice.value = result.existed
      ? `Lekce ${lesson.id} už je task ${result.task.id}.`
      : `Lekce ${lesson.id} je task ${result.task.id}${result.committed ? ', commitnutý do base' : ''}. Spusť ho v Backlogu.`
  } catch (e) {
    if (e instanceof ApiError && e.code === 'project_required') {
      projectFor.value = lesson.id
      project.value = projectOptions.value[0]?.value ?? ''
    } else {
      error.value = errorText(e)
    }
  } finally {
    acting.value = null
  }
  await load()
}

async function dismiss(lesson: Lesson): Promise<void> {
  if (busy.value) return
  acting.value = lesson.id
  notice.value = null
  error.value = null
  try {
    await dismissLesson(lesson.id)
    if (projectFor.value === lesson.id) projectFor.value = null
  } catch (e) {
    error.value = errorText(e)
  } finally {
    acting.value = null
  }
  await load()
}

function runs(n: number): string {
  return `${n} ${plural(n, 'běh', 'běhy', 'běhů')}`
}

function inRuns(n: number): string {
  return `${n} ${plural(n, 'běhu', 'bězích', 'bězích')}`
}

onMounted(() => void load())
onBeforeUnmount(() => {
  generation++
  clearTimeout(timer)
})
</script>

<template>
  <CollapsibleSection ref="section" v-model:open="open" heading="Lekce" class="lessons" data-test="lessons">
    <template #aside>
      <div class="scan-controls">
        <Tooltip text="Projde výtky běhů všech rep v dashboardu a každou lekci uloží do repa, kam pravidlo patří.">
          <label class="all-repos">
            <input v-model="allRepos" type="checkbox" class="switch" role="switch" :disabled="scanning || busy" data-test="lessons-all" />
            Ze všech rep
          </label>
        </Tooltip>
        <button type="button" class="btn" :disabled="scanning || busy" data-test="lessons-scan" @click="findLessons">
          <Search :size="14" aria-hidden="true" /> Najít lekce
        </button>
      </div>
    </template>
    <p class="hint">
      Výtky, které se opakují v bězích, seskupí agent learner do lekcí. Přijatá lekce se stane taskem, který pravidlo zapíše do
      repa; po merge jeho PR tu uvidíš, jestli se výtka ještě objevuje.
    </p>
    <p v-if="scanning" class="status" data-test="lessons-scanning"><Spinner /> Agent learner hledá lekce ve výtkách běhů…</p>
    <p v-else-if="scan?.state === 'failed'" class="error" data-test="lessons-scan-error">{{ scan.error }}</p>
    <p v-else-if="scan?.state === 'done' && scan.result" class="status" data-test="lessons-scan-done">
      Hledání {{ fmtTime(scan.finished_at) }}: {{ scan.result.objections }} výtek z {{ runs(scan.result.runs) }},
      <template v-if="scan.all && scan.result.repos">ze všech rep ({{ scan.result.repos }}), </template>
      lekcí: {{ scan.result.lessons }}<template v-if="scan.result.repeats">, opakování přijatých lekcí: {{ scan.result.repeats }}</template>.
    </p>
    <p v-if="elsewhere.length" class="notice" data-test="lessons-elsewhere">
      Do jiných rep se uložilo {{ lessonsCount(elsewhereTotal) }}:
      <template v-for="([repo, n], i) in elsewhere" :key="repo"
        ><template v-if="i">, </template
        ><a :href="lessonsHref(repo)" class="mono" data-test="lessons-elsewhere-link" :data-repo="repo">{{ repo }}</a> ({{ n }})</template
      >. Najdeš je v sekci Lekce toho repa.
    </p>
    <p v-for="(w, i) in scanWarnings" :key="`w-${i}`" class="dim" data-test="lessons-scan-warning">{{ w }}</p>
    <p v-if="error" class="error" data-test="lessons-error">{{ error }}</p>
    <p v-if="loadError" class="error" data-test="lessons-load-error">Lekce se nepodařilo načíst: {{ loadError }}</p>
    <p v-if="notice" class="notice" data-test="lessons-notice">{{ notice }}</p>
    <p v-if="loading" class="status"><Spinner /> Načítám lekce…</p>
    <p v-else-if="!lessons.length && !scanning" class="empty" data-test="lessons-empty">
      Zatím žádné lekce. Najít lekce projde výtky všech běhů repa, se Ze všech rep i ostatních rep v dashboardu.
    </p>

    <ul v-if="proposed.length" class="list">
      <li v-for="lesson in proposed" :key="lesson.id" class="lesson" data-test="lesson" :data-lesson="lesson.id" data-state="proposed">
        <p class="rule" data-test="lesson-rule">{{ lesson.rule }}</p>
        <p class="meta">
          <span class="mono">{{ lesson.id }}</span> · do <span class="mono" data-test="lesson-target">{{ targetText(lesson) }}</span>
          · <span data-test="lesson-occurrences">{{ runs(lesson.occurrences) }}</span>
          <template v-if="lesson.origin?.length">
            ·
            <Tooltip :text="originTip(lesson)">
              <span class="origin" data-test="lesson-origin-chips">
                <span v-for="repo in lesson.origin" :key="repo" class="chip mono" data-test="lesson-origin">{{ repo }}</span>
              </span>
            </Tooltip>
          </template>
        </p>
        <ul class="complaints" data-test="lesson-complaints">
          <li v-for="(c, i) in lesson.complaints" :key="`${c.run_id}-${i}`">
            <span v-if="c.repo" class="chip mono" data-test="lesson-complaint-repo">{{ c.repo }}</span>
            <a :href="complaintRunHref(c)" class="mono" data-test="lesson-run">{{ c.run_id }}</a>
            <a :href="complaintTaskHref(c)" class="mono task">{{ c.task_id }}</a>
            <span class="source">{{ SOURCE_TEXT[c.source] ?? c.source }}</span>
            <span class="text">{{ c.text }}</span>
          </li>
        </ul>
        <div v-if="projectFor === lesson.id" class="project" data-test="lesson-project">
          <span>Z běhů nejde poznat projekt. Vyber, kam task patří:</span>
          <SelectMenu v-model="project" :options="projectOptions" label="Projekt" data-test="lesson-project-select" />
          <button type="button" class="btn" :disabled="!project || busy" data-test="lesson-project-accept" @click="accept(lesson, project)">
            Přijmout do projektu
          </button>
        </div>
        <div class="actions">
          <button type="button" class="btn primary" :disabled="busy" data-test="lesson-accept" @click="accept(lesson)">
            <Spinner v-if="acting === lesson.id" /> Přijmout
          </button>
          <button type="button" class="btn" :disabled="busy" data-test="lesson-dismiss" @click="dismiss(lesson)">Zamítnout</button>
        </div>
      </li>
    </ul>

    <template v-if="accepted.length">
      <h3>Přijaté</h3>
      <ul class="list">
        <li v-for="lesson in accepted" :key="lesson.id" class="lesson" data-test="lesson" :data-lesson="lesson.id" data-state="accepted">
          <p class="rule">{{ lesson.rule }}</p>
          <p class="meta">
            <span class="mono">{{ lesson.id }}</span> · do <span class="mono">{{ targetText(lesson) }}</span>
            <template v-if="lesson.task_id"> · task <a :href="taskHref(lesson.task_id)" class="mono" data-test="lesson-task">{{ lesson.task_id }}</a></template>
            <template v-if="lesson.pr"> · <a :href="lesson.pr.url" target="_blank" rel="noopener">PR</a></template>
            <template v-if="lesson.origin?.length">
              ·
              <Tooltip :text="originTip(lesson)">
                <span class="origin" data-test="lesson-origin-chips">
                  <span v-for="repo in lesson.origin" :key="repo" class="chip mono" data-test="lesson-origin">{{ repo }}</span>
                </span>
              </Tooltip>
            </template>
          </p>
          <p v-if="lesson.effect" class="effect" data-test="lesson-effect">
            Před merge PR ({{ fmtTime(lesson.effect.merged_at) }}) se výtka objevila v
            <strong data-test="lesson-before">{{ inRuns(lesson.effect.before.runs) }}</strong>, po něm v
            <strong data-test="lesson-after">{{ inRuns(lesson.effect.after.runs) }}</strong>.
            <span class="dim">Výtky po merge doplní další Najít lekce.</span>
          </p>
          <p v-else class="dim" data-test="lesson-waiting">
            {{ runs(lesson.occurrences) }} s výtkou. Účinek se ukáže po merge PR tasku.
          </p>
        </li>
      </ul>
    </template>

    <details v-if="rejected.length" class="rejected" data-test="lessons-rejected">
      <summary>Zamítnuté ({{ rejected.length }})</summary>
      <ul>
        <li v-for="lesson in rejected" :key="lesson.id">
          <span class="mono">{{ lesson.id }}</span> {{ lesson.rule }}<template v-if="lesson.reason"> – {{ lesson.reason }}</template>
        </li>
      </ul>
    </details>
  </CollapsibleSection>
</template>

<style scoped>
.lessons {
  margin-top: 22px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font: inherit;
  font-size: 14px;
  cursor: pointer;
}

.scan-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
}

.all-repos {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--dim);
  font-size: 14px;
  cursor: pointer;
}

.origin {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
  vertical-align: middle;
}

.chip {
  display: inline-block;
  padding: 0 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel);
  color: var(--text);
  font-size: 12px;
  line-height: 18px;
}

.btn:disabled {
  cursor: default;
  opacity: 0.7;
}

.btn.primary {
  border-color: var(--blue);
}

.hint,
.dim,
.empty {
  color: var(--dim);
}

.hint {
  margin: 0 0 10px;
}

.status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
  color: var(--dim);
}

.error {
  color: var(--red);
}

.notice {
  color: var(--green);
}

h3 {
  margin: 18px 0 8px;
  font-size: 15px;
}

.list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.lesson {
  padding: 12px 16px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel-2);
}

.rule {
  margin: 0 0 4px;
  font-weight: 600;
}

.meta {
  margin: 0 0 8px;
  color: var(--dim);
  font-size: 14px;
}

.mono {
  font-family: var(--mono, monospace);
}

.complaints {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin: 0 0 10px;
  padding-left: 18px;
  font-size: 14px;
}

.complaints li {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}

.source {
  color: var(--dim);
}

.text {
  flex: 1 1 320px;
}

.project {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  margin: 0 0 10px;
}

.actions {
  display: flex;
  gap: 8px;
}

.effect {
  margin: 0;
}

.rejected {
  margin-top: 14px;
  color: var(--dim);
}
</style>
