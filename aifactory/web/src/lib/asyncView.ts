import { defineAsyncComponent, type Component } from 'vue'
import AsyncLoadState from '@/components/ui/AsyncLoadState.vue'

/** Keep infrequent screens out of the initial bundle, with visible loading and recovery. */
export function asyncView(loader: () => Promise<Component>) {
  return defineAsyncComponent({ loader, loadingComponent: AsyncLoadState, errorComponent: AsyncLoadState, delay: 150, timeout: 30_000 })
}
