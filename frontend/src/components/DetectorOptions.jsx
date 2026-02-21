import { Card } from './ui/card'
import { Slider } from './ui/slider'
import { Separator } from './ui/separator'

const GAP_OPTIONS = [1, 2, 3]

export default function DetectorOptions({
  sensitivity,
  maxGap,
  onSensitivityChange,
  onMaxGapChange,
}) {
  return (
    <Card>
      {/* ── Sensitivity ─────────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="font-syne font-semibold text-sm" style={{ color: '#e2e2f0' }}>
            Sensitivity
          </span>
          <span className="font-mono text-sm" style={{ color: '#ff3b5c' }}>
            {sensitivity.toFixed(1)}
          </span>
        </div>

        <Slider
          min={0.5}
          max={3.0}
          step={0.1}
          value={[sensitivity]}
          onValueChange={([val]) => onSensitivityChange(val)}
        />

        <div className="flex justify-between mt-2">
          <span className="font-mono text-xs" style={{ color: '#5a5a7a' }}>Fewer flags</span>
          <span className="font-mono text-xs" style={{ color: '#5a5a7a' }}>More flags</span>
        </div>
      </div>

      <Separator className="my-5" />

      {/* ── Max Gap ─────────────────────────────────────────────────────── */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <span className="font-syne font-semibold text-sm" style={{ color: '#e2e2f0' }}>
            Max Gap
          </span>
          <span className="font-mono text-sm" style={{ color: '#ff3b5c' }}>
            {maxGap}
          </span>
        </div>

        <div className="flex gap-2">
          {GAP_OPTIONS.map((val) => {
            const active = maxGap === val
            return (
              <button
                key={val}
                onClick={() => onMaxGapChange(val)}
                className="flex-1 py-1.5 rounded-lg font-mono text-sm font-bold transition-colors"
                style={
                  active
                    ? { background: '#ff3b5c', color: '#fff', border: '1px solid #ff3b5c' }
                    : { background: 'transparent', color: '#5a5a7a', border: '1px solid #1e1e2e' }
                }
              >
                {val}
              </button>
            )
          })}
        </div>

        <p className="font-mono text-xs mt-3" style={{ color: '#5a5a7a' }}>
          Consecutive normal chunks bridged into anomaly regions
        </p>
      </div>
    </Card>
  )
}
