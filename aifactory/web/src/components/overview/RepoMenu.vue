<script setup lang="ts">
// The three-dot menu of a repo in the overview (a card or a calm row); it holds the removal of the
// repo from the dashboard. Closes on a click outside, on Escape and after choosing an item.
import { onBeforeUnmount, ref } from 'vue'
import { MoreVertical, Trash2 } from 'lucide-vue-next'

withDefaults(defineProps<{ name: string; removing?: boolean; itemTest?: string }>(), {
  removing: false,
  itemTest: 'card-remove',
})
const emit = defineEmits<{ remove: [] }>()

const root = ref<HTMLElement | null>(null)
const open = ref(false)

function onOutside(event: Event) {
  const target = event.target as Node | null
  if (target && root.value?.contains(target)) return
  close()
}

function onKeydown(event: Event) {
  if ((event as KeyboardEvent).key === 'Escape') close()
}

function listen(on: boolean) {
  const method = on ? 'addEventListener' : 'removeEventListener'
  document[method]('mousedown', onOutside, true)
  document[method]('keydown', onKeydown)
}

function close() {
  if (!open.value) return
  open.value = false
  listen(false)
}

function toggle() {
  if (open.value) {
    close()
    return
  }
  open.value = true
  listen(true)
}

function remove() {
  close()
  emit('remove')
}

onBeforeUnmount(() => listen(false))
</script>

<template>
  <div ref="root" class="repo-menu">
    <button
      type="button"
      class="menu-button"
      aria-haspopup="menu"
      :aria-expanded="open ? 'true' : 'false'"
      :aria-label="`Akce repozitáře ${name}`"
      data-test="repo-menu"
      @click="toggle"
    >
      <MoreVertical :size="16" aria-hidden="true" />
    </button>
    <div v-if="open" class="menu" role="menu" data-test="repo-menu-items">
      <button
        type="button"
        role="menuitem"
        class="item remove"
        :disabled="removing"
        :data-test="itemTest"
        @click="remove"
      >
        <Trash2 :size="14" aria-hidden="true" /> Odebrat repozitář
      </button>
    </div>
  </div>
</template>

<style scoped>
.repo-menu {
  position: relative;
  flex: none;
}

.menu-button {
  display: inline-flex;
  align-items: center;
  padding: 3px 4px;
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--dim);
  cursor: pointer;
}

.menu-button:hover,
.menu-button[aria-expanded='true'] {
  border-color: var(--border);
  background: var(--panel);
  color: var(--text);
}

.menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  z-index: var(--z-dropdown);
  display: flex;
  flex-direction: column;
  min-width: 200px;
  padding: 4px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  box-shadow: var(--shadow-pop);
}

.item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border: none;
  border-radius: 6px;
  background: transparent;
  font: inherit;
  font-size: 14px;
  text-align: left;
  white-space: nowrap;
  cursor: pointer;
}

.item:hover {
  background: rgba(108, 182, 255, 0.14);
}

.remove {
  color: var(--red);
}

.item:disabled {
  cursor: default;
  opacity: 0.7;
}
</style>
