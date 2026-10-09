// Helpers for driving the shared SelectMenu dropdown in component tests.
// The list is teleported to <body>, so options are looked up there, through the
// trigger's aria-controls.
import { flushPromises, type VueWrapper } from '@vue/test-utils'

function listFor(trigger: Element): HTMLElement | null {
  const id = trigger.getAttribute('aria-controls')
  return id ? document.getElementById(id) : null
}

/** Options of every open dropdown list. */
export function listOptions(): HTMLElement[] {
  return [...document.body.querySelectorAll<HTMLElement>('[data-test="select-list"] [role="option"]')]
}

/** Visible labels of the options of every open dropdown list. */
export function optionLabels(): string[] {
  return listOptions().map((o) => o.textContent?.trim() ?? '')
}

/** Opens the dropdown under `selector` and returns its options. */
export async function openSelect(wrapper: VueWrapper, selector: string): Promise<HTMLElement[]> {
  const trigger = wrapper.get(selector)
  if (trigger.attributes('aria-expanded') !== 'true') await trigger.trigger('click')
  await flushPromises()
  const list = listFor(trigger.element)
  if (!list) throw new Error(`dropdown ${selector} did not open`)
  return [...list.querySelectorAll<HTMLElement>('[role="option"]')]
}

/** Labels of the options offered by the dropdown under `selector`; closes it again. */
export async function selectLabels(wrapper: VueWrapper, selector: string): Promise<string[]> {
  const labels = (await openSelect(wrapper, selector)).map((o) => o.textContent?.trim() ?? '')
  await wrapper.get(selector).trigger('keydown', { key: 'Escape' })
  return labels
}

/** Picks the option with `value` from the dropdown under `selector` with the mouse. */
export async function chooseOption(wrapper: VueWrapper, selector: string, value: string): Promise<void> {
  const options = await openSelect(wrapper, selector)
  const option = options.find((o) => o.dataset.value === value)
  if (!option) throw new Error(`dropdown ${selector} has no option ${JSON.stringify(value)}`)
  option.dispatchEvent(new MouseEvent('click', { bubbles: true }))
  await flushPromises()
}
