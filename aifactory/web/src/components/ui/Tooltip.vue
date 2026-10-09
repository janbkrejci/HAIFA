<script setup lang="ts">
// Shared tooltip — replaces native `title` tooltips across the dashboard.
// Wrapper mode: wraps the slot and shows on hover and keyboard focus.
// Controlled mode (`anchor` prop, e.g. SVG graph nodes): shows next to `anchor` while set.
// The bubble is teleported to <body> with position: fixed, so it sits above the
// sticky topbar and is never clipped by a scroll container or an SVG.
import { computed, nextTick, onBeforeUnmount, reactive, ref, watch } from 'vue'

let seq = 0

const props = withDefaults(
  defineProps<{
    text: string
    anchor?: Element | null
    placement?: 'bottom' | 'top'
  }>(),
  { anchor: undefined, placement: 'bottom' },
)

const id = `tooltip-${++seq}`
const anchorEl = ref<HTMLElement | null>(null)
const bubble = ref<HTMLElement | null>(null)
const hovered = ref(false)
const dismissed = ref(false)
const pos = reactive({ top: 0, left: 0, measured: false })

const controlled = computed(() => props.anchor !== undefined)
const target = computed<Element | null>(() => (controlled.value ? (props.anchor ?? null) : anchorEl.value))
const visible = computed(
  () => !!props.text && !dismissed.value && (controlled.value ? !!props.anchor : hovered.value),
)

const GAP = 8

async function place() {
  pos.measured = false
  await nextTick()
  const el = target.value
  const b = bubble.value
  if (!el || !b) return
  const r = el.getBoundingClientRect()
  const bb = b.getBoundingClientRect()
  const below = r.bottom + GAP
  const above = r.top - bb.height - GAP
  const fitsBelow = below + bb.height <= window.innerHeight - GAP
  const fitsAbove = above >= GAP
  let top = props.placement === 'top' ? (fitsAbove || !fitsBelow ? above : below) : fitsBelow || !fitsAbove ? below : above
  top = Math.max(GAP, top)
  const maxLeft = Math.max(GAP, window.innerWidth - bb.width - GAP)
  const left = Math.min(Math.max(r.left + r.width / 2 - bb.width / 2, GAP), maxLeft)
  pos.top = top
  pos.left = left
  pos.measured = true
}

function dismiss() {
  dismissed.value = true
}

function listen(on: boolean) {
  const method = on ? 'addEventListener' : 'removeEventListener'
  window[method]('scroll', dismiss, true)
  window[method]('resize', dismiss)
}

watch(visible, (now) => {
  listen(now)
  if (now) void place()
})

watch(
  () => props.anchor,
  () => {
    dismissed.value = false
    if (visible.value) void place()
  },
)

watch(
  () => props.text,
  () => {
    if (visible.value) void place()
  },
)

function show() {
  dismissed.value = false
  hovered.value = true
}

function hide() {
  hovered.value = false
}

onBeforeUnmount(() => listen(false))
</script>

<template>
  <span
    v-if="!controlled"
    ref="anchorEl"
    class="tip-anchor"
    data-test="tip-anchor"
    :aria-describedby="visible ? id : undefined"
    @mouseenter="show"
    @mouseleave="hide"
    @focusin="show"
    @focusout="hide"
    @keydown.esc="hide"
  >
    <slot />
  </span>
  <Teleport to="body">
    <div
      v-if="visible"
      :id="id"
      ref="bubble"
      role="tooltip"
      class="tooltip"
      data-test="tooltip"
      :style="{ top: `${pos.top}px`, left: `${pos.left}px`, visibility: pos.measured ? 'visible' : 'hidden' }"
    >
      {{ text }}
    </div>
  </Teleport>
</template>

<style scoped>
.tip-anchor {
  display: inline-flex;
  align-items: center;
  min-width: 0;
}

.tooltip {
  position: fixed;
  z-index: var(--z-tooltip);
  max-width: 320px;
  padding: 6px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel-2);
  color: var(--text);
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 400;
  line-height: 1.35;
  text-align: left;
  box-shadow: var(--shadow-pop);
  pointer-events: none;
  white-space: pre-line;
  overflow-wrap: anywhere;
  animation: tip-in 0.1s ease-out;
}

@keyframes tip-in {
  from {
    opacity: 0;
  }
}
</style>
