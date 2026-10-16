<script setup lang="ts">
// A page section with one heading style that collapses by its heading: the heading is a
// button with aria-expanded and aria-controls, so the mouse, Enter and Space toggle it. The
// content stays mounted while collapsed (v-show), so a form or a table keeps its state.
// `v-model:open` lets the page open a section it navigates to.
import { useId } from 'vue'
import { ChevronDown } from 'lucide-vue-next'

defineProps<{ heading: string }>()
const open = defineModel<boolean>('open', { default: true })
const bodyId = `section-${useId()}`
</script>

<template>
  <section class="collapsible" :data-open="open ? 'true' : 'false'">
    <div class="section-head">
      <h2 class="section-title">
        <button type="button" class="toggle" :aria-expanded="open ? 'true' : 'false'" :aria-controls="bodyId"
          data-test="section-toggle" @click="open = !open">
          <ChevronDown :size="16" aria-hidden="true" class="chevron" :class="{ closed: !open }" />
          <span>{{ heading }}</span>
        </button>
      </h2>
      <slot name="aside" />
    </div>
    <div v-show="open" :id="bodyId" class="section-body" data-test="section-body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.section-head {
  display: flex;
  align-items: center;
  gap: 18px;
  margin: 0 0 10px;
}

.section-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: var(--text);
}

.toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 2px 4px 2px 0;
  border: 0;
  border-radius: 6px;
  background: none;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.toggle:focus-visible {
  outline: 2px solid var(--blue);
  outline-offset: 2px;
}

.chevron {
  flex: none;
  color: var(--dim);
  transition: transform 0.15s ease;
}

.chevron.closed {
  transform: rotate(-90deg);
}
</style>
