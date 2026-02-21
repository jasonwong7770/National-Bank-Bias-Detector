import { motion, LayoutGroup } from 'framer-motion'

function ArrowIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="5" y1="12" x2="19" y2="12" />
      <polyline points="12 5 19 12 12 19" />
    </svg>
  )
}

function Spinner() {
  return (
    <span
      className="inline-block rounded-full border-2"
      style={{
        width: 16,
        height: 16,
        borderColor: 'rgba(255,255,255,0.25)',
        borderTopColor: '#fff',
        animation: 'spin 0.7s linear infinite',
      }}
    />
  )
}

export default function AnalyseButton({ onClick, isLoading, disabled }) {
  const noFile = disabled && !isLoading

  return (
    <>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>

      <motion.button
        layout
        onClick={!disabled && !isLoading ? onClick : undefined}
        className="w-full flex items-center justify-center gap-3 rounded-xl py-4 font-syne font-semibold text-base tracking-widest transition-opacity"
        style={
          noFile
            ? { background: '#15151f', color: '#5a5a7a', border: '1px solid #1e1e2e', cursor: 'not-allowed' }
            : isLoading
            ? { background: '#c72e49', color: '#fff', border: '1px solid #c72e49', cursor: 'default', pointerEvents: 'none' }
            : { background: '#ff3b5c', color: '#fff', border: '1px solid #ff3b5c', cursor: 'pointer' }
        }
        whileHover={!disabled && !isLoading ? { opacity: 0.88 } : {}}
        whileTap={!disabled && !isLoading ? { scale: 0.985 } : {}}
        transition={{ type: 'spring', stiffness: 300, damping: 22 }}
      >
        <motion.span layout className="flex items-center gap-3">
          {isLoading ? (
            <>
              <Spinner />
              <span>Uploading...</span>
            </>
          ) : noFile ? (
            <span>Select a CSV to continue</span>
          ) : (
            <>
              <span>Upload File</span>
              <ArrowIcon />
            </>
          )}
        </motion.span>
      </motion.button>
    </>
  )
}
