import { cn } from '@/lib/utils'

export function Card({ className, children, style }) {
  return (
    <div
      className={cn('rounded-xl border p-5', className)}
      style={{ background: '#15151f', borderColor: '#1e1e2e', ...style }}
    >
      {children}
    </div>
  )
}
