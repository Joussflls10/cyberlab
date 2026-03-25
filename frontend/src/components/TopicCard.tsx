import ChallengeCard from './ChallengeCard'

interface Topic {
  id: string
  title: string
  description: string
  challenges: number
  completed: number
}

interface TopicCardProps {
  topic: Topic
}

export default function TopicCard({ topic }: TopicCardProps) {
  return (
    <div className="border border-border rounded-lg bg-surface p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <h3 className="text-lg font-semibold text-primary">{topic.title}</h3>
          <p className="text-gray-400 text-sm mt-1">{topic.description}</p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-bold text-secondary">{topic.completed}/{topic.challenges}</div>
          <div className="text-xs text-gray-500">challenges completed</div>
        </div>
      </div>
      <div className="flex gap-3">
        {Array.from({ length: Math.min(3, topic.challenges) }).map((_, i) => (
          <ChallengeCard
            key={i}
            challenge={{
              id: `${topic.id}-challenge-${i + 1}`,
              title: `Challenge ${i + 1}`,
              difficulty: i === 0 ? 'easy' : i === 1 ? 'medium' : 'hard',
              completed: i < topic.completed
            }}
          />
        ))}
        {topic.challenges > 3 && (
          <div className="flex items-center justify-center w-32 border border-border rounded-lg bg-background text-gray-500 text-sm">
            +{topic.challenges - 3} more
          </div>
        )}
      </div>
    </div>
  )
}
