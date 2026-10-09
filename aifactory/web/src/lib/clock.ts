// A reactive "now" for live durations: ticks every second, only while active.
import { onScopeDispose, ref, watch, type Ref } from 'vue'

/** Reactive epoch ms: ticks every `intervalMs` while `active()` is true; stops on unmount. */
export function useNow(active: () => boolean, intervalMs = 1000): Ref<number> {
  const now = ref(Date.now())
  let timer: ReturnType<typeof setInterval> | undefined

  function stop() {
    if (timer !== undefined) clearInterval(timer)
    timer = undefined
  }

  watch(
    active,
    (on) => {
      stop()
      now.value = Date.now()
      if (on) timer = setInterval(() => (now.value = Date.now()), intervalMs)
    },
    { immediate: true },
  )
  onScopeDispose(stop)
  return now
}
