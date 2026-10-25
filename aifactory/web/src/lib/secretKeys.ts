/** A fresh detector per mounted dashboard; repeats never advance or reset it. */
export function createSecretKeys() {
  const sequence = ['Control', 'Shift', 'Control', 'Shift']
  let position = 0
  let previous = 0
  return (event: Pick<KeyboardEvent, 'key' | 'repeat'>, now = performance.now()): boolean => {
    if (event.repeat) return false
    if (now - previous > 1000) position = 0
    previous = now
    if (event.key !== sequence[position]) {
      position = event.key === sequence[0] ? 1 : 0
      return false
    }
    position++
    if (position !== sequence.length) return false
    position = 0
    return true
  }
}
