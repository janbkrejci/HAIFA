import { beforeEach as beforeLocaleTest, afterEach as afterLocaleTest } from 'vitest'
import { setLocale, t } from '@/lib/i18n'

beforeLocaleTest(() => setLocale('cs'))
afterLocaleTest(() => setLocale('en'))

import { describe, expect, it } from 'vitest'
import { useConfirm } from './confirm'

describe('useConfirm', () => {
  it('resolves true on confirm and false on cancel', async () => {
    const c = useConfirm()
    const yes = c.ask({ title: 'A?' })
    expect(c.dialog.open).toBe(true)
    expect(c.dialog.title).toBe('A?')
    expect(c.dialog.confirmLabel).toBe('Potvrdit')
    expect(c.dialog.cancelLabel).toBe('Zrušit')
    c.confirm()
    expect(c.dialog.open).toBe(false)
    await expect(yes).resolves.toBe(true)
    const no = c.ask({ title: 'B?', tone: 'danger' })
    expect(c.dialog.tone).toBe('danger')
    c.cancel()
    await expect(no).resolves.toBe(false)
  })

  it('cancels a question still open when asked again', async () => {
    const c = useConfirm()
    const first = c.ask({ title: 'A?', message: 'pozn.' })
    const second = c.ask({ title: 'B?' })
    await expect(first).resolves.toBe(false)
    expect(c.dialog.message).toBe('')
    c.confirm()
    await expect(second).resolves.toBe(true)
  })
})


it('keeps a pending question and its answer while translated labels update', async () => {
  setLocale('en')
  const c = useConfirm()
  const answer = c.ask(() => ({ title: t('leave.title'), message: t('leave.message') }))
  expect(c.dialog.title).toBe('Discard unsaved changes?')
  expect(c.dialog.confirmLabel).toBe('Confirm')
  setLocale('cs')
  expect(c.dialog.open).toBe(true)
  expect(c.dialog.title).toBe('Zahodit neuložené změny?')
  expect(c.dialog.message).toContain('Rozepsané změny')
  expect(c.dialog.confirmLabel).toBe('Potvrdit')
  expect(c.dialog.cancelLabel).toBe('Zrušit')
  c.confirm()
  await expect(answer).resolves.toBe(true)
})
