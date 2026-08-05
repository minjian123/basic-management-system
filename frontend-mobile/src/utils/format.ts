export function formatDate(input: Date | string | number): string {
  const date = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(date.getTime())) {
    return ''
  }
  const pad = (n: number): string => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

export function isBlank(text: string | null | undefined): boolean {
  return text === null || text === undefined || text.trim() === ''
}
