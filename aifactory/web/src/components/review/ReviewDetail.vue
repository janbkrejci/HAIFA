<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import DetailSection from '@/components/runs/DetailSection.vue'
import StatusChip from '@/components/runs/StatusChip.vue'
import MarkdownView from '@/components/ui/MarkdownView.vue'
import { fmtCost, fmtTime, fmtTokens } from '@/lib/format'
import { runHref, taskHref } from '@/lib/router'
import {
  doneLabel,
  isReadOnly,
  mergedByAuto,
  type ReviewAction,
  type ReviewDetail,
} from '@/lib/review'
import ChecksList from './ChecksList.vue'
import DiffView from './DiffView.vue'
import MergeabilityChip from './MergeabilityChip.vue'
import ReviewActions from './ReviewActions.vue'
import ReviewVerdict from './ReviewVerdict.vue'
import CodeTip from '@/components/ui/CodeTip.vue'
import { levelNoun } from '@/lib/backlog'
import { useLevels } from '@/lib/names'

const props = defineProps<{
  detail: ReviewDetail
  busy: boolean
  pending?: ReviewAction | null
  /** Bumped after a return succeeded (clears the note). */
  returned?: number
}>()
const emit = defineEmits<{ approve: []; return: [note: string]; resolve: [] }>()

// Every section starts collapsed and collapses again when another PR is shown.
// A silent refresh of the same PR (same task_id) keeps what the user opened.
const open = reactive({
  body: false,
  runs: false,
  checks: false,
  review: false,
  diff: false,
})

function collapseAll() {
  for (const key of Object.keys(open) as (keyof typeof open)[]) open[key] = false
}

watch(() => props.detail.task_id, collapseAll)

function isLocal(url: string): boolean {
  return url.startsWith('local:')
}

/** A merged or closed PR is read only: no approve, return, resolve or rebase. */
const readOnly = computed(() => isReadOnly(props.detail))
const doneState = computed(() =>
  props.detail.provider_state === 'merged' || props.detail.provider_state === 'closed'
    ? props.detail.provider_state
    : props.detail.pr.state,
)

const level = useLevels()
/** `projekt`, `modul`, … by the top level of `levels`. */
const projectNoun = computed(() => {
  const levels = Array.isArray(props.detail.levels) ? props.detail.levels : []
  return levelNoun(levels[0] ?? level.top.value)
})

const runs = () => (Array.isArray(props.detail.runs) ? props.detail.runs : [])
const checks = () => (Array.isArray(props.detail.checks) ? props.detail.checks : [])
</script>

<template>
  <article class="review-detail">
    <header class="head">
      <h2 data-test="task-label">
        <a :href="taskHref(detail.task_id)" class="task-id">{{ detail.task_id }}</a
        ><span v-if="detail.task_title">{{ ' ' + detail.task_title }}</span>
      </h2>
      <p class="meta">
        <span data-test="project"
          >{{ projectNoun }}
          <CodeTip v-if="detail.project_id" :code="detail.project_id" /><template v-else>—</template></span
        >
        <span class="mono">{{ detail.pr.branch }} → {{ detail.pr.base }}</span>
        <MergeabilityChip :value="detail.mergeability" />
        <span>stav PR {{ detail.provider_state ?? '—' }}</span>
        <span class="mono" data-test="cost">{{ fmtCost(detail.cost) }} · {{ fmtTokens(detail.tokens) }} tok.</span>
        <span v-if="isLocal(detail.pr.url)" class="mono" data-test="pr-link">{{ detail.pr.url }}</span>
        <a v-else :href="detail.pr.url" target="_blank" rel="noopener" data-test="pr-link">
          PR #{{ detail.pr.pr_id }}
        </a>
      </p>
    </header>

    <div class="actions-bar" data-test="actions">
      <p v-if="!readOnly && detail.pr.auto_merge_error" class="auto-error" data-test="auto-merge-error">
        Auto-merge nesloučil: {{ detail.pr.auto_merge_error }} – schval ručně.
      </p>
      <p v-if="readOnly" class="readonly" data-test="read-only">
        PR je {{ doneLabel(doneState) }}
        <span v-if="detail.pr.merged_at ?? detail.pr.updated_at" class="dim"
          >({{ fmtTime(detail.pr.merged_at ?? detail.pr.updated_at) }})</span
        >
        – jen pro čtení, akce nejsou dostupné.
        <span v-if="mergedByAuto(detail.pr)" class="auto-chip" data-test="merged-by-auto"
          >Sloučil auto-merge</span
        >
      </p>
      <ReviewActions
        v-else
        :detail="detail"
        :busy="busy"
        :pending="pending"
        :returned="returned"
        @approve="emit('approve')"
        @return="(n) => emit('return', n)"
        @resolve="emit('resolve')"
      />
    </div>

    <DetailSection title="Popis PR" :open="open.body" @toggle="open.body = !open.body">
      <MarkdownView :source="detail.pr.body ?? ''" data-test="pr-body" />
    </DetailSection>

    <DetailSection title="Běhy" :count="runs().length" :open="open.runs" @toggle="open.runs = !open.runs">
      <p v-if="!runs().length" class="faint">Žádné běhy</p>
      <ul v-else class="runs">
        <li v-for="r in runs()" :key="r.run_id">
          <a :href="runHref(r.run_id)" class="mono" data-test="run-link">{{ r.run_id }}</a>
          <span>{{ r.workflow ?? '—' }}</span>
          <StatusChip :status="r.state" />
          <span class="dim">{{ fmtTime(r.started_at) }}</span>
          <span class="mono">{{ fmtCost(r.cost) }}</span>
          <span v-if="r.note" class="faint">poznámka: {{ r.note }}</span>
          <span v-if="r.error" class="err">{{ r.error }}</span>
        </li>
      </ul>
    </DetailSection>

    <DetailSection title="Gates a testy" :count="checks().length" :open="open.checks" @toggle="open.checks = !open.checks">
      <ChecksList :checks="checks()" />
    </DetailSection>

    <DetailSection title="Verdikt revieweru" :open="open.review" @toggle="open.review = !open.review">
      <ReviewVerdict :verdict="detail.review ?? null" />
    </DetailSection>

    <DetailSection
      title="Diff"
      :count="detail.diff?.stat.files ?? 0"
      :open="open.diff"
      @toggle="open.diff = !open.diff"
    >
      <DiffView v-if="detail.diff" :key="detail.task_id" :diff="detail.diff" />
    </DetailSection>
  </article>
</template>

<style scoped>
.head {
  margin-bottom: 16px;
}

h2 {
  margin: 0 0 6px;
  font-size: 20px;
}

.meta {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  margin: 0;
  color: var(--dim);
}

.task-id,
.mono {
  font-family: var(--mono);
}

.actions-bar {
  margin-bottom: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--border-soft);
}

.readonly {
  margin: 0;
  color: var(--dim);
}

.auto-chip {
  margin-left: 8px;
  padding: 1px 8px;
  border: 1px solid rgba(90, 210, 221, 0.45);
  border-radius: 999px;
  font-size: 13px;
  color: var(--cyan);
}

.auto-error {
  margin: 0 0 10px;
  color: var(--amber);
}

.runs {
  list-style: none;
  margin: 0;
  padding: 0;
}

.runs li {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  padding: 4px 0;
}

.err {
  color: var(--red);
}
</style>
