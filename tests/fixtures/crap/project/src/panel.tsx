export function pick(on: boolean) {
  return on ? 'a' : 'b'
}

export function Panel({ items }: { items: string[] }) {
  const label = (s: string) => (s ? s : '-')
  return items.length > 0 && label(items[0])
}
