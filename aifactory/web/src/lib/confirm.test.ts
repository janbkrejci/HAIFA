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
