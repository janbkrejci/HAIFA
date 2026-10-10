<script setup lang="ts">
import { Check, TriangleAlert } from 'lucide-vue-next'
import { useReadiness } from '@/lib/readiness'
import { useRemoveRepo } from '@/lib/repos'
import Spinner from '@/components/ui/Spinner.vue'
import RemoveRepoDialog from '@/components/repos/RemoveRepoDialog.vue'
import Tooltip from '@/components/ui/Tooltip.vue'

withDefaults(defineProps<{ chip?: boolean }>(), { chip: false })
const emit = defineEmits<{ changed: [] }>()
const { phase, issues, recheck } = useReadiness()
const removal = useRemoveRepo(() => { emit('changed'); recheck() })
const { remove, removing, error: removeError } = removal
defineExpose({ recheck })
function openHarnesses() { window.dispatchEvent(new Event('harness-settings-open')) }
</script>

<template>
  <template v-if="chip">
    <span v-if="phase === 'checking'" class="status-chip checking" role="status" data-test="readiness-checking"><Spinner /> Probíhá kontrola</span>
    <Tooltip v-else-if="phase === 'success'" text="Spustit kontrolu znovu"><button type="button" class="status-chip success" data-test="readiness-success" @click="recheck"><Check :size="14" aria-hidden="true" /> Systém v pořádku</button></Tooltip>
    <a v-else href="#/problems" class="status-chip warning" data-test="readiness-warning"><TriangleAlert :size="14" aria-hidden="true" /> Nalezeny problémy</a>
  </template>
  <div v-else class="readiness" :class="phase" :role="phase === 'warning' ? 'alert' : 'status'" :data-test="`readiness-${phase}`">
    <p v-if="phase === 'checking'"><Spinner /> Probíhá kontrola</p>
    <p v-else-if="phase === 'success'"><Check :size="18" aria-hidden="true" /> Systém v pořádku</p>
    <template v-else>
      <p><TriangleAlert :size="18" aria-hidden="true" /> Nalezeny problémy</p>
      <ul>
        <li v-for="(issue, index) in issues" :key="index">
          <strong>{{ issue.title }}</strong>
          <span>{{ issue.hint }}</span>
          <button v-if="issue.repo" type="button" class="action" :disabled="removing !== null" @click="remove(issue.repo)">{{ issue.action }}</button>
          <button v-else-if="issue.href === '#harness-settings'" type="button" class="action" @click="openHarnesses">{{ issue.action }}</button>
          <a v-else :href="issue.href" class="action">{{ issue.action }}</a>
        </li>
      </ul>
      <p v-if="removeError" role="alert">{{ removeError }}</p>
    </template>
    <button v-if="phase !== 'checking'" type="button" class="action" data-test="readiness-retry" @click="recheck">Zkontrolovat znovu</button>
  </div>
  <RemoveRepoDialog :removal="removal" />
</template>

<style scoped>
.status-chip { display: inline-flex; align-items: center; gap: 6px; border: 1px solid currentColor; border-radius: 999px; padding: 5px 10px; font: inherit; font-size: 12px; white-space: nowrap; background: var(--panel-2); text-decoration: none; }
button.status-chip, a.status-chip { cursor: pointer; }
.status-chip:hover { background: var(--surface); }
.checking { color: var(--blue); }
.success { color: var(--green); }
.warning { color: var(--amber); }
.readiness { padding: 16px; border: 1px solid currentColor; border-radius: 10px; background: var(--panel-2); margin-bottom: 18px; }
.readiness p { display: flex; align-items: center; gap: 8px; margin: 0; font-weight: 600; }
ul { display: flex; flex-direction: column; gap: 14px; padding: 0; list-style: none; color: var(--text); }
li { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }
li span { color: var(--dim); }
.action { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; color: var(--text); background: var(--surface); font: inherit; cursor: pointer; }
</style>
