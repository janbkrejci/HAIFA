<script setup lang="ts">
import './ui/statusIconChip.css'
import { Check, TriangleAlert } from 'lucide-vue-next'
import { useReadiness } from '@/lib/readiness'
import { useRemoveRepo } from '@/lib/repos'
import Spinner from '@/components/ui/Spinner.vue'
import RemoveRepoDialog from '@/components/repos/RemoveRepoDialog.vue'
import Tooltip from '@/components/ui/Tooltip.vue'
import TryDemoButton from '@/components/demo/TryDemoButton.vue'

withDefaults(defineProps<{ chip?: boolean }>(), { chip: false })
const emit = defineEmits<{ changed: [] }>()
const { phase, issues, recheck, refresh } = useReadiness()
const removal = useRemoveRepo(() => { emit('changed'); refresh() })
const { remove, removing, error: removeError } = removal
defineExpose({ recheck })
function openHarnesses() { window.dispatchEvent(new Event('harness-settings-open')) }
</script>

<template>
  <template v-if="chip">
    <Tooltip v-if="phase === 'loading'" text="Načítání stavu"><span class="status-icon-chip checking" role="status" tabindex="0" aria-label="Načítání stavu" data-test="readiness-loading"><Spinner /></span></Tooltip>
    <Tooltip v-else-if="phase === 'checking'" text="Probíhá kontrola"><span class="status-icon-chip checking" role="status" tabindex="0" aria-label="Probíhá kontrola" data-test="readiness-checking"><Spinner /></span></Tooltip>
    <Tooltip v-else-if="phase === 'success'" text="Systém v pořádku – kliknutím spustíš kontrolu znovu"><button type="button" class="status-icon-chip success" aria-label="Systém v pořádku – kliknutím spustíš kontrolu znovu" data-test="readiness-success" @click="recheck"><Check :size="14" aria-hidden="true" /></button></Tooltip>
    <Tooltip v-else-if="phase === 'warning'" text="Nalezeny problémy – kliknutím otevřeš seznam problémů"><a href="#/problems" class="status-icon-chip warning" aria-label="Nalezeny problémy – kliknutím otevřeš seznam problémů" data-test="readiness-warning"><TriangleAlert :size="14" aria-hidden="true" /></a></Tooltip>
  </template>
  <div v-else-if="phase" class="readiness" :class="phase" :role="phase === 'warning' ? 'alert' : 'status'" :data-test="`readiness-${phase}`">
    <p v-if="phase === 'loading'"><Spinner /> Načítání stavu</p>
    <p v-else-if="phase === 'checking'"><Spinner /> Probíhá kontrola</p>
    <p v-else-if="phase === 'success'"><Check :size="18" aria-hidden="true" /> Systém v pořádku</p>
    <template v-else>
      <p><TriangleAlert :size="18" aria-hidden="true" /> Nalezeny problémy</p>
      <ul>
        <li v-for="(issue, index) in issues" :key="index">
          <strong>{{ issue.title }}</strong>
          <span>{{ issue.hint }}</span>
          <button v-if="issue.repo" type="button" class="action" :disabled="removing !== null" @click="remove(issue.repo)">{{ issue.action }}</button>
          <button v-else-if="issue.href === '#harness-settings'" type="button" class="action" @click="openHarnesses">{{ issue.action }}</button>
          <span v-else class="actions">
            <a :href="issue.href" class="action">{{ issue.action }}</a>
            <TryDemoButton v-if="issue.id === 'repo'" @started="emit('changed')" />
          </span>
        </li>
      </ul>
      <p v-if="removeError" role="alert">{{ removeError }}</p>
    </template>
    <button v-if="phase !== 'checking' && phase !== 'loading'" type="button" class="action" data-test="readiness-retry" @click="recheck">Zkontrolovat znovu</button>
  </div>
  <RemoveRepoDialog :removal="removal" />
</template>

<style scoped>
.checking { color: var(--blue); }
.success { color: var(--green); }
.warning { color: var(--amber); }
.readiness { padding: 16px; border: 1px solid currentColor; border-radius: 10px; background: var(--panel-2); margin-bottom: 18px; }
.readiness p { display: flex; align-items: center; gap: 8px; margin: 0; font-weight: 600; }
ul { display: flex; flex-direction: column; gap: 14px; padding: 0; list-style: none; color: var(--text); }
li { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }
li span { color: var(--dim); }
.actions { display: inline-flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.action { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; padding: 6px 12px; color: var(--text); background: var(--surface); font: inherit; cursor: pointer; }
</style>
