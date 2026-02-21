import * as SeparatorPrimitive from '@radix-ui/react-separator'

export function Separator({ className, orientation = 'horizontal', ...props }) {
  return (
    <SeparatorPrimitive.Root
      orientation={orientation}
      className={className}
      style={{
        background: '#1e1e2e',
        height: orientation === 'horizontal' ? '1px' : '100%',
        width: orientation === 'vertical' ? '1px' : '100%',
        flexShrink: 0,
      }}
      {...props}
    />
  )
}
