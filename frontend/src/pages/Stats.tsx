import { useState, useEffect } from 'react'
import { getProgressStats, getActivityHeatmap, getCourses } from '../api/client'

interface ProgressStats {
  totalChallengesCompleted: number
  currentStreak: number
  successRate: number
  totalTimeSpent: number
  challengesByDifficulty: {
    easy: number
    medium: number
    hard: number
  }
  challengesByType: {
    command: number
    output: number
    file: number
  }
  weakAreas: Array<{
    topic: string
    successRate: number
    attempts: number
  }>
}

interface ActivityDay {
  date: string
  count: number
}

interface Course {
  id: string
  title: string
  description: string
  topics: Array<{
    id: string
    title: string
    challenges: Array<{
      id: string
      title: string
      completed: boolean
    }>
  }>
}

interface CourseProgress {
  course: Course
  completedTopics: number
  totalTopics: number
  lastAccessed: string
}

interface Achievement {
  id: string
  name: string
  description: string
  icon: string
  earned: boolean
  earnedAt?: string
}

const ACHIEVEMENTS: Achievement[] = [
  { id: 'first_challenge', name: 'First Blood', description: 'Complete your first challenge', icon: '🎯', earned: false },
  { id: 'streak_7', name: 'Week Warrior', description: '7 day streak', icon: '🔥', earned: false },
  { id: 'streak_30', name: 'Monthly Master', description: '30 day streak', icon: '👑', earned: false },
  { id: 'challenges_10', name: 'Decathlete', description: 'Complete 10 challenges', icon: '⚡', earned: false },
  { id: 'challenges_50', name: 'Half Century', description: 'Complete 50 challenges', icon: '💎', earned: false },
  { id: 'challenges_100', name: 'Centurion', description: 'Complete 100 challenges', icon: '🏆', earned: false },
  { id: 'perfect_week', name: 'Flawless', description: '100% success rate for a week', icon: '✨', earned: false },
  { id: 'course_complete', name: 'Course Complete', description: 'Finish your first course', icon: '📚', earned: false },
]

function getActivityLevel(count: number): number {
  if (count === 0) return 0
  if (count <= 2) return 1
  if (count <= 5) return 2
  if (count <= 10) return 3
  return 4
}

function getHeatmapColor(level: number): string {
  const colors = [
    '#1a1a1a',  // level 0 - no activity
    '#00ff8833', // level 1 - light green
    '#00ff8866', // level 2 - medium green
    '#00ff8899', // level 3 - bright green
    '#00ff88',   // level 4 - full green
  ]
  return colors[level]
}

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric'
  })
}

function formatTime(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  if (hours === 0) return `${mins}m`
  if (mins === 0) return `${hours}h`
  return `${hours}h ${mins}m`
}

function generateLastYearDays(): ActivityDay[] {
  const days: ActivityDay[] = []
  const today = new Date()
  const lastYear = new Date(today)
  lastYear.setDate(lastYear.getDate() - 364)
  
  for (let d = new Date(lastYear); d <= today; d.setDate(d.getDate() + 1)) {
    days.push({
      date: d.toISOString().split('T')[0],
      count: 0
    })
  }
  return days
}

export default function Stats() {
  const [stats, setStats] = useState<ProgressStats | null>(null)
  const [activity, setActivity] = useState<ActivityDay[]>([])
  const [courseProgress, setCourseProgress] = useState<CourseProgress[]>([])
  const [achievements, setAchievements] = useState<Achievement[]>(ACHIEVEMENTS)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const [statsData, activityData, coursesData] = await Promise.all([
          getProgressStats(),
          getActivityHeatmap(),
          getCourses()
        ])

        // Process stats
        setStats(statsData)

        // Process activity heatmap - merge with last year days
        const lastYearDays = generateLastYearDays()
        const activityMap = new Map((activityData as ActivityDay[]).map(d => [d.date, d.count]))
        const mergedActivity: ActivityDay[] = lastYearDays.map(day => ({
          date: day.date,
          count: activityMap.get(day.date) || 0
        }))
        setActivity(mergedActivity)

        // Process course progress
        const progress = coursesData.map((course: Course) => {
          const completedTopics = course.topics.filter(topic =>
            topic.challenges.every(ch => ch.completed)
          ).length
          return {
            course,
            completedTopics,
            totalTopics: course.topics.length,
            lastAccessed: new Date().toISOString() // TODO: Get from API
          }
        })
        setCourseProgress(progress)

        // Process achievements
        const earnedAchievements = ACHIEVEMENTS.map(ach => {
          let earned = false
          if (ach.id === 'first_challenge' && statsData.totalChallengesCompleted >= 1) earned = true
          if (ach.id === 'streak_7' && statsData.currentStreak >= 7) earned = true
          if (ach.id === 'streak_30' && statsData.currentStreak >= 30) earned = true
          if (ach.id === 'challenges_10' && statsData.totalChallengesCompleted >= 10) earned = true
          if (ach.id === 'challenges_50' && statsData.totalChallengesCompleted >= 50) earned = true
          if (ach.id === 'challenges_100' && statsData.totalChallengesCompleted >= 100) earned = true
          if (ach.id === 'course_complete' && progress.some((p: CourseProgress) => p.completedTopics === p.totalTopics)) earned = true
          return { ...ach, earned }
        })
        setAchievements(earnedAchievements)

      } catch (error) {
        console.error('Failed to load stats:', error)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-primary text-lg">
          <span className="cursor-blink">_</span> Loading dashboard...
        </div>
      </div>
    )
  }

  if (!stats) {
    return (
      <div className="text-center py-12">
        <p className="text-error text-xl">Failed to load stats</p>
      </div>
    )
  }

  // Group activity by week for heatmap display
  const weeks: ActivityDay[][] = []
  let currentWeek: ActivityDay[] = []
  let dayOfWeek = new Date(activity[0]?.date || new Date()).getDay()
  
  // Pad beginning to start on Sunday
  for (let i = 0; i < dayOfWeek; i++) {
    currentWeek.unshift({ date: '', count: 0 })
  }
  
  activity.forEach((day, idx) => {
    currentWeek.push(day)
    if (currentWeek.length === 7 || idx === activity.length - 1) {
      weeks.push(currentWeek)
      currentWeek = []
    }
  })

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="border-b border-border pb-4">
        <h2 className="text-3xl font-bold text-primary">
          <span className="text-secondary">./</span>stats_dashboard
          <span className="cursor-blink ml-2">_</span>
        </h2>
        <p className="text-gray-500 mt-2">User Progress & Analytics</p>
      </div>

      {/* Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="border border-primary/30 rounded bg-surface p-6 hover:border-primary transition-colors">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-gray-400 text-sm">Challenges Completed</h3>
            <span className="text-2xl">💀</span>
          </div>
          <p className="text-4xl font-bold text-primary">{stats.totalChallengesCompleted}</p>
          <p className="text-gray-500 text-xs mt-2">Total hacks executed</p>
        </div>

        <div className="border border-secondary/30 rounded bg-surface p-6 hover:border-secondary transition-colors">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-gray-400 text-sm">Current Streak</h3>
            <span className="text-2xl">🔥</span>
          </div>
          <p className="text-4xl font-bold text-secondary">{stats.currentStreak}</p>
          <p className="text-gray-500 text-xs mt-2">Days in a row</p>
        </div>

        <div className="border border-primary/30 rounded bg-surface p-6 hover:border-primary transition-colors">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-gray-400 text-sm">Success Rate</h3>
            <span className="text-2xl">🎯</span>
          </div>
          <p className="text-4xl font-bold text-primary">{stats.successRate.toFixed(1)}%</p>
          <p className="text-gray-500 text-xs mt-2">Accuracy rating</p>
        </div>

        <div className="border border-secondary/30 rounded bg-surface p-6 hover:border-secondary transition-colors">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-gray-400 text-sm">Time Spent</h3>
            <span className="text-2xl">⏱️</span>
          </div>
          <p className="text-4xl font-bold text-secondary">{formatTime(stats.totalTimeSpent)}</p>
          <p className="text-gray-500 text-xs mt-2">Total learning time</p>
        </div>
      </div>

      {/* Activity Heatmap */}
      <div className="border border-border rounded-lg bg-surface p-6">
        <h3 className="text-xl font-semibold text-primary mb-4 flex items-center gap-2">
          <span>📊</span> Activity Heatmap
        </h3>
        <div className="overflow-x-auto">
          <div className="flex gap-1 min-w-max">
            <div className="flex flex-col gap-1 mr-2">
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(day => (
                <div key={day} className="h-3 text-xs text-gray-500 flex items-center">
                  {day}
                </div>
              ))}
            </div>
            <div className="flex gap-1">
              {weeks.map((week, weekIdx) => (
                <div key={weekIdx} className="flex flex-col gap-1">
                  {week.map((day, dayIdx) => (
                    <div
                      key={dayIdx}
                      className="w-3 h-3 rounded-sm"
                      style={{
                        backgroundColor: getHeatmapColor(getActivityLevel(day.count)),
                        opacity: day.date ? 1 : 0
                      }}
                      title={day.date ? `${day.date}: ${day.count} challenges` : ''}
                    />
                  ))}
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 mt-4 text-xs text-gray-500">
          <span>Less</span>
          <div className="flex gap-1">
            {[0, 1, 2, 3, 4].map(level => (
              <div
                key={level}
                className="w-3 h-3 rounded-sm"
                style={{ backgroundColor: getHeatmapColor(level) }}
              />
            ))}
          </div>
          <span>More</span>
        </div>
      </div>

      {/* Course Progress */}
      <div className="border border-border rounded-lg bg-surface p-6">
        <h3 className="text-xl font-semibold text-primary mb-4 flex items-center gap-2">
          <span>📚</span> Course Progress
        </h3>
        <div className="space-y-4">
          {courseProgress.map(({ course, completedTopics, totalTopics, lastAccessed }) => {
            const percentage = totalTopics > 0 ? (completedTopics / totalTopics) * 100 : 0
            return (
              <div key={course.id} className="border border-border rounded p-4 hover:border-primary/50 transition-colors">
                <div className="flex items-center justify-between mb-2">
                  <div>
                    <h4 className="text-lg font-semibold text-primary">{course.title}</h4>
                    <p className="text-gray-500 text-sm">{course.description}</p>
                  </div>
                  <div className="text-right">
                    <p className="text-2xl font-bold text-secondary">{percentage.toFixed(0)}%</p>
                    <p className="text-gray-500 text-xs">
                      Last accessed: {formatDate(lastAccessed)}
                    </p>
                  </div>
                </div>
                <div className="w-full bg-background border border-border rounded-full h-3 overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-500"
                    style={{ width: `${percentage}%` }}
                  />
                </div>
                <p className="text-gray-500 text-xs mt-2">
                  {completedTopics}/{totalTopics} topics completed
                </p>
              </div>
            )
          })}
        </div>
      </div>

      {/* Skill Breakdown */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Challenges by Difficulty */}
        <div className="border border-border rounded-lg bg-surface p-6">
          <h3 className="text-xl font-semibold text-primary mb-4 flex items-center gap-2">
            <span>⚡</span> Challenges by Difficulty
          </h3>
          <div className="space-y-4">
            {[
              { label: 'Easy', value: stats.challengesByDifficulty.easy, color: 'text-primary' },
              { label: 'Medium', value: stats.challengesByDifficulty.medium, color: 'text-secondary' },
              { label: 'Hard', value: stats.challengesByDifficulty.hard, color: 'text-error' },
            ].map(({ label, value, color }) => {
              const total = stats.challengesByDifficulty.easy + stats.challengesByDifficulty.medium + stats.challengesByDifficulty.hard
              const percentage = total > 0 ? (value / total) * 100 : 0
              return (
                <div key={label}>
                  <div className="flex justify-between mb-1">
                    <span className={`text-sm ${color}`}>{label}</span>
                    <span className="text-gray-400 text-sm">{value} ({percentage.toFixed(1)}%)</span>
                  </div>
                  <div className="w-full bg-background border border-border rounded-full h-2 overflow-hidden">
                    <div
                      className={`h-full ${color.replace('text-', 'bg-')} transition-all duration-300`}
                      style={{ width: `${percentage}%` }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Challenges by Type */}
        <div className="border border-border rounded-lg bg-surface p-6">
          <h3 className="text-xl font-semibold text-primary mb-4 flex items-center gap-2">
            <span>🔧</span> Challenges by Type
          </h3>
          <div className="space-y-4">
            {[
              { label: 'Command', value: stats.challengesByType.command, icon: '💻' },
              { label: 'Output', value: stats.challengesByType.output, icon: '📝' },
              { label: 'File', value: stats.challengesByType.file, icon: '📁' },
            ].map(({ label, value, icon }) => {
              const total = stats.challengesByType.command + stats.challengesByType.output + stats.challengesByType.file
              const percentage = total > 0 ? (value / total) * 100 : 0
              return (
                <div key={label} className="flex items-center gap-4">
                  <span className="text-2xl">{icon}</span>
                  <div className="flex-1">
                    <div className="flex justify-between mb-1">
                      <span className="text-sm text-gray-300">{label}</span>
                      <span className="text-gray-400 text-sm">{value} ({percentage.toFixed(1)}%)</span>
                    </div>
                    <div className="w-full bg-background border border-border rounded-full h-2 overflow-hidden">
                      <div
                        className="h-full bg-secondary transition-all duration-300"
                        style={{ width: `${percentage}%` }}
                      />
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Weak Areas */}
      {stats.weakAreas.length > 0 && (
        <div className="border border-border rounded-lg bg-surface p-6">
          <h3 className="text-xl font-semibold text-error mb-4 flex items-center gap-2">
            <span>⚠️</span> Weak Areas (Focus Here)
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {stats.weakAreas.slice(0, 6).map((area, idx) => (
              <div key={idx} className="border border-error/30 rounded p-4 bg-background/50">
                <h4 className="text-primary font-semibold mb-2">{area.topic}</h4>
                <div className="flex justify-between items-center">
                  <span className="text-gray-400 text-sm">{area.attempts} attempts</span>
                  <span className="text-error font-bold">{area.successRate.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-background border border-border rounded-full h-2 overflow-hidden mt-2">
                  <div
                    className="h-full bg-error transition-all duration-300"
                    style={{ width: `${area.successRate}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Achievements */}
      <div className="border border-border rounded-lg bg-surface p-6">
        <h3 className="text-xl font-semibold text-primary mb-4 flex items-center gap-2">
          <span>🏅</span> Achievements
        </h3>
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-8 gap-4">
          {achievements.map(ach => (
            <div
              key={ach.id}
              className={`flex flex-col items-center p-4 rounded border transition-all ${
                ach.earned
                  ? 'border-secondary bg-secondary/10 hover:scale-105'
                  : 'border-border bg-background/50 opacity-50'
              }`}
            >
              <span className="text-3xl mb-2">{ach.icon}</span>
              <p className={`text-xs font-semibold text-center ${ach.earned ? 'text-secondary' : 'text-gray-500'}`}>
                {ach.name}
              </p>
              <p className="text-gray-500 text-xs text-center mt-1 hidden lg:block">
                {ach.description}
              </p>
            </div>
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="text-center text-gray-600 text-sm py-4 border-t border-border">
        <p>System Status: <span className="text-primary">Online</span> | Last Sync: {new Date().toLocaleTimeString()}</p>
      </div>
    </div>
  )
}
