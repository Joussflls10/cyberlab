interface ProgressBarProps {
  value: number
  max: number
  className?: string
  color?: 'primary' | 'secondary'
}

export default function ProgressBar({ value, max, className = '', color = 'primary' }: ProgressBarProps) {
  const percentage = Math.min(100, Math.max(0, (value / max) * 100))
  
  const colorClasses = {
    primary: 'bg-primary',
    secondary: 'bg-secondary'
  }

  return (
    <div className={`w-full bg-background border border-border rounded-full h-2 overflow-hidden ${className}`}>
      <div
        className={`h-full ${colorClasses[color]} transition-all duration-300`}
        style={{ width: `${percentage}%` }}
      />
    </div>
  )
}
