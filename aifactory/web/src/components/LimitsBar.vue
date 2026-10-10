<script setup lang="ts">
// Free session limits of Claude and Codex in the topbar: per window a thin bar that fills
// from the left with the used share (neutral colour, not a success one) and the free percent.
// A failed read shows stale windows or an explicit unavailable status.
import { computed } from 'vue'
import { TriangleAlert } from 'lucide-vue-next'
import { pct, unavailableTip, windowTip, type LimitProvider } from '../lib/limits'
import Spinner from './ui/Spinner.vue'
import Tooltip from './ui/Tooltip.vue'

const props = withDefaults(defineProps<{ providers: LimitProvider[]; loading?: boolean; usable?: boolean }>(), { usable: undefined })
const empty = computed(() => !props.loading && !(props.usable ?? props.providers.length > 0))
const emit = defineEmits<{ open: [] }>()
// Keep a stable visual order even when API results arrive in another order.
const orderedProviders = computed(() =>
  [...props.providers].sort((a, b) => Number(a.harness === 'codex') - Number(b.harness === 'codex')),
)
</script>

<template>
  <button type="button" class="limits-trigger" :class="{ 'harness-loading': loading, 'harness-empty': empty }" :aria-busy="loading || undefined" aria-label="Usage limity a nastavení harnessů" data-test="harness-settings-open" @click="emit('open')">
  <span v-if="loading" class="harness-status"><Spinner />Harnessy</span>
  <span v-else-if="empty" class="harness-status"><TriangleAlert :size="14" aria-hidden="true" />Nakonfigurujte harnessy</span>
  <span v-else-if="!providers.length">Harnessy</span>
  <span v-else class="compact-label">Harnessy</span>
  <div v-if="!loading && !empty && providers.length" class="limits" data-test="limits">
    <div
      v-for="provider in orderedProviders"
      :key="provider.harness"
      class="limit-provider"
      :data-test="`limits-${provider.harness}`"
    >
      <span class="limit-name">{{ provider.label }}</span>
      <div class="limit-windows">
        <Tooltip v-if="!provider.windows.length" :text="unavailableTip(provider)">
          <span tabindex="0" :aria-label="unavailableTip(provider)" :data-test="`limits-${provider.harness}-unavailable`">nedostupné</span>
        </Tooltip>
        <span v-else-if="provider.stale && provider.harness !== 'claude'" data-test="limits-stale">zastaralé</span>
        <Tooltip v-for="window in provider.windows" :key="window.id" :text="windowTip(provider, window)">
          <span class="limit-window" tabindex="0" :data-test="`limit-${provider.harness}-${window.id}`">
            <span class="limit-label">{{ window.label }}</span>
            <span
              class="limit-track"
              role="progressbar"
              aria-valuemin="0"
              aria-valuemax="100"
              :aria-valuenow="pct(window.used)"
              :aria-label="windowTip(provider, window)"
            >
              <span class="limit-fill" :style="{ width: `${pct(window.used)}%` }" data-test="limit-fill" />
            </span>
            <span class="limit-left" data-test="limit-left">{{ pct(window.left) }}&nbsp;%</span>
          </span>
        </Tooltip>
      </div>
    </div>
  </div>
  </button>
</template>

<style scoped>
.limits-trigger { background: none; border: 1px solid transparent; border-radius: 8px; color: var(--dim); font: inherit; padding: 4px 8px; cursor: pointer; text-align: left; }
.limits-trigger:hover, .limits-trigger:focus-visible { border-color: var(--border); background: var(--panel-2); }
.harness-status { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; font-size: 12px; }
/* loading and empty look like the other topbar status chips */
.limits-trigger.harness-loading, .limits-trigger.harness-empty { display: inline-flex; align-items: center; border: 1px solid currentColor; border-radius: 999px; padding: 5px 10px; font-size: 12px; background: var(--panel-2); }
.limits-trigger.harness-loading { color: var(--blue); }
.limits-trigger.harness-empty { color: var(--red); }
.compact-label { display: none; }
.limits {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
  color: var(--faint);
  font-size: 12px;
  white-space: nowrap;
  min-width: 0;
}

.limit-provider {
  display: grid;
  grid-template-columns: 4em minmax(0, 1fr);
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}

.limit-windows {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  min-width: 0;
}

.limit-name {
  color: var(--dim);
}

.limit-window {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  outline: none;
}

.limit-window:focus-visible {
  border-radius: 4px;
  box-shadow: 0 0 0 1px var(--border);
}

.limit-track {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 4px;
  border-radius: 2px;
  background: var(--panel-2);
  box-shadow: inset 0 0 0 1px var(--border);
  overflow: hidden;
}

.limit-fill {
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  background: var(--faint);
  border-radius: 2px;
}

@media (max-width: 1180px) {
  .compact-label { display: inline; }
  .limits {
    display: none;
  }
}

.limit-left {
  min-width: 3.2em;
  font-variant-numeric: tabular-nums;
}
</style>
