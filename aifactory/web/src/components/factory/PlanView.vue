<script setup lang="ts">
// The preview of a reviewed plan, shared by the factory, library and onboarding operations:
// what it says first (slot), warnings, blockers, library items and the files with their diffs.
import { computed } from 'vue'
import type { FactoryFile, PlanBlocker, PlanItem, PlanWarning } from '@/lib/api'
import { fileActionText, planCodeText } from '@/lib/factory'
import DiffContent from '@/components/review/DiffContent.vue'

export interface PreviewPlan {
  files?: FactoryFile[] | null
  blockers?: PlanBlocker[] | null
  warnings?: PlanWarning[] | null
  envelopeWarnings?: string[] | null
  items?: PlanItem[] | null
}

const props = withDefaults(defineProps<{
  plan: PreviewPlan
  title?: string | null
  /** Files folded into <details> (long library plans) instead of open diffs. */
  collapsed?: boolean
}>(), { title: null, collapsed: false })

const warnings = computed(() =>
  [...(props.plan.warnings ?? []), ...(props.plan.envelopeWarnings ?? [])].map((w) => (typeof w === 'string' ? w : w.message)),
)
</script>

<template>
  <section class="plan-view">
    <h2 v-if="title">{{ title }}</h2>
    <slot />
    <p v-for="(w, i) in warnings" :key="i" class="warning" data-test="plan-warning">Varování: {{ w }}</p>
    <p v-for="b in plan.blockers ?? []" :key="b.code" role="alert" class="error" data-test="plan-blocker">
      {{ planCodeText(b.code) }}: {{ b.message }}<template v-if="b.fix"> Oprava: {{ b.fix }}</template>
    </p>
    <ul v-if="plan.items?.length" class="items" data-test="plan-items">
      <li v-for="i in plan.items" :key="`${i.type}/${i.name}`">
        {{ i.type }}/{{ i.name }} · {{ planCodeText(i.action) }}<template v-if="i.version"> · {{ i.version }}</template>
      </li>
    </ul>
    <template v-for="file in plan.files ?? []" :key="file.path">
      <details v-if="collapsed" data-test="plan-file">
        <summary>{{ fileActionText(file.action) }} {{ file.path }} <small v-if="file.mode">{{ file.mode }}</small></summary>
        <DiffContent :binary="file.binary" :patch="file.diff" :content="file.content" />
      </details>
      <article v-else data-test="plan-file">
        <h3>{{ file.path }} · {{ fileActionText(file.action) }} <small v-if="file.mode">{{ file.mode }}</small></h3>
        <DiffContent :binary="file.binary" :patch="file.diff" :content="file.content" />
      </article>
    </template>
  </section>
</template>

<style scoped>
.plan-view { max-width: 100%; overflow-wrap: anywhere; }
.warning { color: var(--amber); }
.error { color: var(--red); }
article { margin: 14px 0; }
details { margin: 8px 0; }
h3 { font-size: 15px; }
</style>
