import * as SliderPrimitive from '@radix-ui/react-slider'
import { cn } from '@/lib/utils'

export function Slider({ className, ...props }) {
  return (
    <SliderPrimitive.Root
      className={cn('relative flex w-full touch-none select-none items-center', className)}
      {...props}
    >
      <SliderPrimitive.Track
        className="relative h-1 w-full grow overflow-hidden rounded-full"
        style={{ background: '#1e1e2e' }}
      >
        <SliderPrimitive.Range
          className="absolute h-full rounded-full"
          style={{ background: '#ff3b5c' }}
        />
      </SliderPrimitive.Track>
      <SliderPrimitive.Thumb
        className="block h-4 w-4 rounded-full border-2 shadow transition-colors focus-visible:outline-none disabled:pointer-events-none disabled:opacity-50"
        style={{ background: '#ff3b5c', borderColor: '#ff3b5c' }}
      />
    </SliderPrimitive.Root>
  )
}
