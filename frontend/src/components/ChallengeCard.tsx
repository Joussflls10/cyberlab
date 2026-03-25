import { Link } from 'react-router-dom'

interface Challenge {
  id: string
  title: string
  difficulty: 'easy' | 'medium' | 'hard'
  completed: boolean
}

interface ChallengeCardProps {
  challenge: Challenge
}

export default function ChallengeCard({ challenge }: ChallengeCardProps) {
  const difficultyColors = {
    easy: 'border-primary text-primary',
    medium: 'border-secondary text-secondary',
    hard: 'border-error text-error'
  }

  const difficultyBg = {
    easy: 'bg-primary/10',
    medium: 'bg-secondary/10',
    hard: 'bg-error/10'
  }

  return (
    <Link to={`/challenge/${challenge.id}`} className="block">
      <div className={`w-32 border ${difficultyColors[challenge.difficulty]} rounded-lg p-4 hover:bg-surface transition-colors ${difficultyBg[challenge.difficulty]}`}>
        <div className="text-xs text-gray-500 mb-2 uppercase">{challenge.difficulty}</div>
        <div className="font-semibold text-sm truncate">{challenge.title}</div>
        {challenge.completed && (
          <div className="text-primary text-xs mt-2">✓ Completed</div>
        )}
      </div>
    </Link>
  )
}
