import { useEffect, useMemo, useState } from 'react'
import { useParams, Link, useNavigate } from 'react-router-dom'
import { getCourse, getTopics, getChallenges, getCourseProgress, deleteCourse } from '../api/client'
import { ChevronDown, ChevronRight, Terminal, FileText, Code, Lock, CheckCircle, Circle, SkipForward, Trash2 } from 'lucide-react'

// Types
interface Challenge {
  id: string
  topic_id: string
  title: string
  description: string
  question: string
  difficulty: 'easy' | 'medium' | 'hard'
  type: 'command' | 'output' | 'file'
  status: 'locked' | 'available' | 'completed' | 'skipped'
  order: number
}

interface Topic {
  id: string
  course_id: string
  title: string
  description: string
  order: number
  challenges?: Challenge[]
}

interface Course {
  id: string
  title: string
  description: string
  created_at: string
  source_document?: string
}

interface CourseProgress {
  course_id: string
  total_challenges: number
  completed_challenges: number
  skipped_challenges: number
  completion_percentage: number
  estimated_time_remaining_minutes: number
}

// Helper functions
function getDifficultyBadgeColor(difficulty: string): string {
  switch (difficulty) {
    case 'easy': return 'bg-primary/20 text-primary border-primary/30'
    case 'medium': return 'bg-secondary/20 text-secondary border-secondary/30'
    case 'hard': return 'bg-error/20 text-error border-error/30'
    default: return 'bg-gray-700/20 text-gray-400 border-gray-600/30'
  }
}

function getStatusIcon(status: string): JSX.Element {
  switch (status) {
    case 'completed':
      return <CheckCircle className="w-4 h-4 text-primary" />
    case 'skipped':
      return <SkipForward className="w-4 h-4 text-gray-500" />
    case 'available':
      return <Circle className="w-4 h-4 text-secondary" />
    case 'locked':
      return <Lock className="w-4 h-4 text-gray-600" />
    default:
      return <Circle className="w-4 h-4 text-gray-600" />
  }
}

function getTypeIcon(type: string): JSX.Element {
  switch (type) {
    case 'command':
      return <Terminal className="w-4 h-4" />
    case 'output':
      return <Code className="w-4 h-4" />
    case 'file':
      return <FileText className="w-4 h-4" />
    default:
      return <Terminal className="w-4 h-4" />
  }
}

function formatDate(dateString: string): string {
  const date = new Date(dateString)
  return date.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  })
}

function formatTime(minutes: number): string {
  if (minutes < 60) {
    return `${minutes} min`
  }
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`
}

// Components
function ChallengeCard({ challenge, onClick }: { challenge: Challenge; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      disabled={challenge.status === 'locked'}
      className={`w-full text-left border rounded-lg p-4 transition-all duration-200 ${
        challenge.status === 'locked'
          ? 'border-gray-800 bg-gray-900/30 opacity-50 cursor-not-allowed'
          : challenge.status === 'completed'
          ? 'border-primary/30 bg-primary/5 hover:border-primary/60 hover:bg-primary/10'
          : challenge.status === 'skipped'
          ? 'border-gray-700 bg-gray-800/30 hover:border-gray-600'
          : 'border-border bg-surface hover:border-secondary/60 hover:bg-surface/80'
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className={`text-xs px-2 py-0.5 rounded border ${getDifficultyBadgeColor(challenge.difficulty)}`}>
              {challenge.difficulty}
            </span>
            <span className="text-gray-500 flex items-center gap-1">
              {getTypeIcon(challenge.type)}
              <span className="text-xs uppercase">{challenge.type}</span>
            </span>
          </div>
          <h4 className={`font-semibold truncate ${
            challenge.status === 'completed' ? 'text-primary' : 'text-gray-100'
          }`}>
            {challenge.title}
          </h4>
          <p className="text-gray-400 text-sm mt-1 line-clamp-2">
            {challenge.question}
          </p>
        </div>
        <div className="flex-shrink-0">
          {getStatusIcon(challenge.status)}
        </div>
      </div>
    </button>
  )
}

function TopicSection({ 
  topic, 
  expanded, 
  onToggle,
  onChallengeOpen,
}: { 
  topic: Topic & { challenges: Challenge[] }; 
  expanded: boolean; 
  onToggle: () => void;
  onChallengeOpen: (challengeId: string) => void;
}) {
  const completedCount = topic.challenges.filter((c: Challenge) => c.status === 'completed').length
  const totalCount = topic.challenges.length
  const progressPercent = totalCount > 0 ? Math.round((completedCount / totalCount) * 100) : 0

  return (
    <div className="border border-border rounded-lg bg-surface overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-surface/80 transition-colors"
      >
        <div className="flex items-center gap-3">
          {expanded ? (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronRight className="w-5 h-5 text-gray-400" />
          )}
          <div className="text-left">
            <h3 className="text-lg font-semibold text-primary">{topic.title}</h3>
            <p className="text-gray-400 text-sm">{topic.description}</p>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <div className="text-right">
            <div className="text-sm text-gray-400">
              {completedCount}/{totalCount} completed
            </div>
            <div className="w-32 h-2 bg-background border border-border rounded-full overflow-hidden mt-1">
              <div 
                className="h-full bg-primary transition-all duration-300"
                style={{ width: `${progressPercent}%` }}
              />
            </div>
          </div>
        </div>
      </button>
      
      {expanded && (
        <div className="border-t border-border p-4 space-y-3">
          {topic.challenges.map((challenge) => (
            <ChallengeCard
              key={challenge.id}
              challenge={challenge}
              onClick={() => onChallengeOpen(challenge.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function ProgressSidebar({ progress }: { progress: CourseProgress }) {
  return (
    <div className="border border-border rounded-lg bg-surface p-6 sticky top-6">
      <h3 className="text-lg font-semibold text-primary mb-4">Progress</h3>
      
      <div className="mb-6">
        <div className="flex items-end justify-between mb-2">
          <span className="text-4xl font-bold text-primary">{progress.completion_percentage}%</span>
          <span className="text-gray-400 text-sm mb-1">complete</span>
        </div>
        <div className="w-full h-3 bg-background border border-border rounded-full overflow-hidden">
          <div 
            className="h-full bg-primary transition-all duration-500"
            style={{ width: `${progress.completion_percentage}%` }}
          />
        </div>
      </div>

      <div className="space-y-3 text-sm">
        <div className="flex justify-between items-center">
          <span className="text-gray-400">Completed</span>
          <span className="text-primary font-semibold">{progress.completed_challenges}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-400">Skipped</span>
          <span className="text-gray-500">{progress.skipped_challenges}</span>
        </div>
        <div className="flex justify-between items-center">
          <span className="text-gray-400">Total</span>
          <span className="text-gray-100 font-semibold">{progress.total_challenges}</span>
        </div>
      </div>

      <div className="border-t border-border mt-6 pt-4">
        <div className="flex justify-between items-center">
          <span className="text-gray-400 text-sm">Est. time remaining</span>
          <span className="text-secondary font-semibold">{formatTime(progress.estimated_time_remaining_minutes)}</span>
        </div>
      </div>
    </div>
  )
}

export default function CoursePage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [course, setCourse] = useState<Course | null>(null)
  const [topics, setTopics] = useState<(Topic & { challenges: Challenge[] })[]>([])
  const [progress, setProgress] = useState<CourseProgress | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expandedTopics, setExpandedTopics] = useState<Set<string>>(new Set())
  const [deleting, setDeleting] = useState(false)

  const orderedChallenges = useMemo(() => {
    return [...topics]
      .sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      .flatMap(topic =>
        [...topic.challenges].sort((a, b) => (a.order ?? 0) - (b.order ?? 0))
      )
  }, [topics])

  const challengeRouteStateFor = (challengeId: string) => {
    const challengeIndex = orderedChallenges.findIndex(challenge => challenge.id === challengeId)
    if (challengeIndex < 0) return undefined

    return {
      courseId: id,
      challengeIndex,
      challengeTotal: orderedChallenges.length,
      challengeIds: orderedChallenges.map(challenge => challenge.id),
    }
  }

  const navigateToChallenge = (challengeId: string) => {
    const state = challengeRouteStateFor(challengeId)
    if (state) {
      navigate(`/challenge/${challengeId}`, { state })
      return
    }

    navigate(`/challenge/${challengeId}`)
  }

  useEffect(() => {
    async function loadCourseData() {
      if (!id) return
      
      try {
        setLoading(true)
        setError(null)
        
        // Load course details
        const courseData = await getCourse(id)
        setCourse(courseData)
        
        // Load topics with challenges
        const topicsData = await getTopics(id)
        const topicsWithChallenges = await Promise.all(
          (topicsData as any[]).map(async (topic: any) => {
            const challengesData = await getChallenges(topic.id)
            const normalizedChallenges: Challenge[] = (challengesData as any[]).map((challenge: any) => ({
              id: challenge.id,
              topic_id: challenge.topic_id,
              title: challenge.title || challenge.question?.slice(0, 80) || 'Challenge',
              description: challenge.description || challenge.question || '',
              question: challenge.question || '',
              difficulty: challenge.difficulty || 'easy',
              type: challenge.type || 'command',
              status: challenge.status || 'available',
              order: challenge.order || 0,
            }))

            return {
              id: topic.id,
              course_id: topic.course_id || id,
              title: topic.title || topic.name || 'Topic',
              description: topic.description || '',
              order: topic.order || 0,
              challenges: normalizedChallenges,
            }
          })
        )
        setTopics(topicsWithChallenges)
        
        // Load progress
        const progressData = await getCourseProgress(id)
        setProgress(progressData)
        
        // Auto-expand first incomplete topic
        const firstIncomplete = topicsWithChallenges.findIndex((t: Topic & { challenges: Challenge[] }) => 
          t.challenges.some((c: Challenge) => c.status !== 'completed')
        )
        if (firstIncomplete >= 0) {
          setExpandedTopics(new Set([topicsWithChallenges[firstIncomplete].id]))
        }
      } catch (error) {
        console.error('Failed to load course:', error)
        setError(error instanceof Error ? error.message : 'Failed to load course data')
      } finally {
        setLoading(false)
      }
    }
    
    loadCourseData()
  }, [id])

  const handleStartNextChallenge = () => {
    const nextChallenge = orderedChallenges.find(
      challenge => challenge.status !== 'completed' && challenge.status !== 'locked'
    )

    if (nextChallenge) {
      navigateToChallenge(nextChallenge.id)
    }
  }

  const handleDeleteCourse = async () => {
    if (!course || !confirm(`Are you sure you want to delete "${course.title}"? This action cannot be undone.`)) {
      return
    }
    
    setDeleting(true)
    try {
      const result = await deleteCourse(course.id)
      if (result.success) {
        navigate('/')
      } else {
        setError(`Failed to delete course: ${result.message}`)
        setDeleting(false)
      }
    } catch (error) {
      setError('Failed to delete course')
      setDeleting(false)
    }
  }

  const toggleTopic = (topicId: string) => {
    setExpandedTopics(prev => {
      const next = new Set(prev)
      if (next.has(topicId)) {
        next.delete(topicId)
      } else {
        next.add(topicId)
      }
      return next
    })
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-primary text-lg">
          <span className="cursor-blink">_</span> Loading course...
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-error text-xl mb-2">Error loading course</p>
        <p className="text-gray-400 text-sm mb-4">{error}</p>
        <Link to="/" className="text-primary hover:underline mt-4 inline-block">
          ← Back to courses
        </Link>
      </div>
    )
  }

  if (!course || !progress) {
    return (
      <div className="text-center py-12">
        <p className="text-error text-xl">Course not found</p>
        <Link to="/" className="text-primary hover:underline mt-4 inline-block">
          ← Back to courses
        </Link>
      </div>
    )
  }

  const totalChallenges = topics.reduce((sum, t) => sum + t.challenges.length, 0)
  const completedChallenges = topics.reduce((sum, t) => 
    sum + t.challenges.filter((c: Challenge) => c.status === 'completed').length, 0
  )

  return (
    <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
      {/* Main Content */}
      <div className="lg:col-span-3 space-y-6">
        <Link to="/" className="text-gray-400 hover:text-primary transition-colors inline-block">
          ← Back to courses
        </Link>

        {/* Course Header */}
        <div className="border border-border rounded-lg bg-surface p-6">
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-4">
            <div className="flex-1">
              <h1 className="text-3xl font-bold text-primary mb-2">{course.title}</h1>
              <p className="text-gray-400 text-lg">{course.description}</p>
            </div>
            <div className="flex w-full sm:w-auto gap-2">
              <button
                onClick={handleDeleteCourse}
                disabled={deleting}
                className="px-4 py-3 border border-error/30 text-error hover:bg-error/10 transition-colors rounded-lg disabled:opacity-50 disabled:cursor-not-allowed"
                title="Delete course"
              >
                <Trash2 className="w-5 h-5" />
              </button>
              <button
                onClick={() => navigate(`/admin/courses/${course.id}/challenges`)}
                className="px-4 py-3 border border-border text-gray-300 hover:border-primary/40 hover:text-primary transition-colors rounded-lg"
                title="Review generated challenges"
              >
                Review Challenges
              </button>
              <button
                onClick={handleStartNextChallenge}
                disabled={completedChallenges >= totalChallenges}
                className="flex-1 sm:flex-none px-6 py-3 bg-primary text-background font-semibold rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {completedChallenges >= totalChallenges ? '✓ Course Complete' : 'Start Next Challenge →'}
              </button>
            </div>
          </div>
          
          <div className="flex items-center gap-6 text-sm text-gray-500 pt-4 border-t border-border">
            <div>
              <span className="text-gray-600">Created:</span>{' '}
              <span className="text-gray-300">{formatDate(course.created_at)}</span>
            </div>
            {course.source_document && (
              <div>
                <span className="text-gray-600">Source:</span>{' '}
                <span className="text-gray-300">{course.source_document}</span>
              </div>
            )}
            <div className="flex items-center gap-2">
              <span className="text-gray-600">Progress:</span>{' '}
              <span className="text-primary font-semibold">{progress.completion_percentage}%</span>
            </div>
          </div>
          
          {/* Overall Progress Bar */}
          <div className="mt-4">
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-400">Overall Progress</span>
              <span className="text-primary font-semibold">
                {completedChallenges}/{totalChallenges} challenges
              </span>
            </div>
            <div className="w-full h-3 bg-background border border-border rounded-full overflow-hidden">
              <div 
                className="h-full bg-primary transition-all duration-500"
                style={{ width: `${progress.completion_percentage}%` }}
              />
            </div>
          </div>
        </div>

        {/* Topics */}
        <div>
          <h2 className="text-xl font-semibold text-secondary mb-4 flex items-center gap-2">
            <ChevronDown className="w-5 h-5" />
            Topics ({topics.length})
          </h2>
          <div className="space-y-4">
            {topics.map((topic) => (
              <TopicSection
                key={topic.id}
                topic={topic}
                expanded={expandedTopics.has(topic.id)}
                onToggle={() => toggleTopic(topic.id)}
                onChallengeOpen={(challengeId) => navigateToChallenge(challengeId)}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Sidebar */}
      <div className="lg:col-span-1">
        {progress && <ProgressSidebar progress={progress} />}
      </div>
    </div>
  )
}
