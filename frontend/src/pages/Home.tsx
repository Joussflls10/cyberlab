import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCourses, getStats, deleteCourse } from '../api/client'
import { Trash2 } from 'lucide-react'
import ProgressBar from '../components/ProgressBar'

interface Course {
  id: string
  title: string
  description: string
  topics: number
  challenges: number
  progress: number
  estimatedTime?: string
  status?: 'not-started' | 'in-progress' | 'completed'
}

interface Stats {
  totalCourses: number
  completedChallenges: number
  currentStreak: number
}

interface Activity {
  id: string
  challengeName: string
  courseName: string
  status: 'completed' | 'attempted' | 'failed'
  timestamp: string
}

export default function Home() {
  const [courses, setCourses] = useState<Course[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [activity, setActivity] = useState<Activity[]>([])
  const [loading, setLoading] = useState(true)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  const loadData = async () => {
    try {
      const [coursesData, statsData] = await Promise.all([
        getCourses(),
        getStats()
      ])
      
      // Map courses with status
      const mappedCourses: Course[] = (coursesData as any[]).map((course: any) => ({
        id: course.id,
        title: course.title,
        description: course.description,
        topics: course.topics || 0,
        challenges: course.challenges || 0,
        progress: course.progress || 0,
        estimatedTime: course.estimatedTime || `${Math.ceil((course.challenges || 0) * 15)} min`,
        status: course.progress === 100 ? 'completed' : course.progress > 0 ? 'in-progress' : 'not-started'
      }))
      
      setCourses(mappedCourses)
      
      // Map stats
      setStats({
        totalCourses: statsData?.totalCourses || mappedCourses.length,
        completedChallenges: statsData?.completedChallenges || 0,
        currentStreak: statsData?.currentStreak || 0
      })
      
      // Mock recent activity (replace with real API when available)
      const mockActivity: Activity[] = [
        { id: '1', challengeName: 'Buffer Overflow Basics', courseName: 'Binary Exploitation', status: 'completed', timestamp: new Date(Date.now() - 3600000).toISOString() },
        { id: '2', challengeName: 'SQL Injection Advanced', courseName: 'Web Security', status: 'attempted', timestamp: new Date(Date.now() - 7200000).toISOString() },
        { id: '3', challengeName: 'XSS Fundamentals', courseName: 'Web Security', status: 'completed', timestamp: new Date(Date.now() - 86400000).toISOString() },
      ]
      setActivity(mockActivity)
    } catch (error) {
      console.error('Failed to load data:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleDeleteCourse = async (e: React.MouseEvent, courseId: string, courseTitle: string) => {
    e.preventDefault()
    e.stopPropagation()
    
    if (!confirm(`Are you sure you want to delete "${courseTitle}"? This action cannot be undone.`)) {
      return
    }
    
    setDeletingId(courseId)
    try {
      const result = await deleteCourse(courseId)
      if (result.success) {
        setCourses(prev => prev.filter(c => c.id !== courseId))
      } else {
        alert(`Failed to delete course: ${result.message}`)
      }
    } catch (error) {
      console.error('Failed to delete course:', error)
      alert('Failed to delete course')
    } finally {
      setDeletingId(null)
    }
  }

  useEffect(() => {
    loadData()
    
    // Poll for new courses every 5 seconds
    const pollInterval = setInterval(loadData, 5000)
    
    return () => clearInterval(pollInterval)
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-primary text-lg">
          <span className="cursor-blink">_</span> Initializing CyberLab...
        </div>
      </div>
    )
  }

  const getStatusBadge = (status: Course['status']) => {
    const badges = {
      'completed': <span className="px-2 py-1 text-xs font-bold bg-primary/20 text-primary rounded">COMPLETED</span>,
      'in-progress': <span className="px-2 py-1 text-xs font-bold bg-secondary/20 text-secondary rounded">IN PROGRESS</span>,
      'not-started': <span className="px-2 py-1 text-xs font-bold bg-gray-700/50 text-gray-400 rounded">NOT STARTED</span>
    }
    return badges[status || 'not-started']
  }

  const getActivityStatusIcon = (status: Activity['status']) => {
    switch (status) {
      case 'completed': return <span className="text-primary">✓</span>
      case 'attempted': return <span className="text-secondary">⟳</span>
      case 'failed': return <span className="text-error">✗</span>
    }
  }

  const formatTimeAgo = (timestamp: string) => {
    const diff = Date.now() - new Date(timestamp).getTime()
    const hours = Math.floor(diff / 3600000)
    const days = Math.floor(diff / 86400000)
    
    if (hours < 1) return 'Just now'
    if (hours < 24) return `${hours}h ago`
    if (days === 1) return 'Yesterday'
    return `${days}d ago`
  }

  // Empty state
  if (courses.length === 0) {
    return (
      <div className="space-y-8">
        {/* Hero Section */}
        <div className="border border-primary/30 rounded-lg bg-surface/50 p-8 relative overflow-hidden">
          <div className="absolute top-0 right-0 p-4 opacity-10">
            <pre className="text-primary text-xs">
{`┌────────────────────────┐
│   CYBERLAB v1.0.0      │
│   TERMINAL ACCESS      │
└────────────────────────┘`}
            </pre>
          </div>
          
          <div className="relative z-10">
            <div className="flex items-center gap-3 mb-4">
              <span className="text-4xl">💀</span>
              <div>
                <h1 className="text-4xl font-bold text-primary">CyberLab</h1>
                <p className="text-gray-400 text-sm">Terminal-Based Security Training Platform</p>
              </div>
            </div>
            
            <div className="flex items-center gap-6 mt-6">
              <Link
                to="/grinder"
                className="inline-flex items-center gap-2 px-6 py-3 bg-primary/20 hover:bg-primary/30 border border-primary text-primary font-bold rounded transition-all hover:scale-105"
              >
                <span>📤</span>
                Upload Document
              </Link>
              
              <div className="flex gap-6 text-sm">
                <div className="text-center">
                  <div className="text-2xl font-bold text-primary">0</div>
                  <div className="text-gray-500">Courses</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-primary">0</div>
                  <div className="text-gray-500">Challenges</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-secondary">0</div>
                  <div className="text-gray-500">Day Streak</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Empty State */}
        <div className="border border-border rounded-lg bg-surface p-12 text-center">
          <div className="text-6xl mb-4">📚</div>
          <h2 className="text-2xl font-bold text-primary mb-2">No Courses Yet</h2>
          <p className="text-gray-400 mb-6 max-w-md mx-auto">
            Upload a document to get started. Our AI will analyze it and generate interactive security challenges.
          </p>
          <Link
            to="/grinder"
            className="inline-flex items-center gap-2 px-6 py-3 bg-primary text-black font-bold rounded hover:bg-primary/90 transition-colors"
          >
            <span>📤</span>
            Upload Your First Document
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <div className="border border-primary/30 rounded-lg bg-surface/50 p-8 relative overflow-hidden">
        <div className="absolute top-0 right-0 p-4 opacity-10">
          <pre className="text-primary text-xs">
{`┌────────────────────────┐
│   CYBERLAB v1.0.0      │
│   TERMINAL ACCESS      │
└────────────────────────┘`}
          </pre>
        </div>
        
        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-4">
            <span className="text-4xl">💀</span>
            <div>
              <h1 className="text-4xl font-bold text-primary">CyberLab</h1>
              <p className="text-gray-400 text-sm">Terminal-Based Security Training Platform</p>
            </div>
          </div>
          
          <div className="flex items-center gap-6 mt-6">
            <Link
              to="/grinder"
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary/20 hover:bg-primary/30 border border-primary text-primary font-bold rounded transition-all hover:scale-105"
            >
              <span>📤</span>
              Upload Document
            </Link>
            
            {stats && (
              <div className="flex gap-6 text-sm">
                <div className="text-center">
                  <div className="text-2xl font-bold text-primary">{stats.totalCourses}</div>
                  <div className="text-gray-500">Courses</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-primary">{stats.completedChallenges}</div>
                  <div className="text-gray-500">Challenges</div>
                </div>
                <div className="text-center">
                  <div className="text-2xl font-bold text-secondary">{stats.currentStreak}</div>
                  <div className="text-gray-500">Day Streak</div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Course Grid */}
      <div>
        <h2 className="text-2xl font-bold text-primary mb-4 flex items-center gap-2">
          <span>📖</span>
          Available Courses
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {courses.map((course) => (
            <div
              key={course.id}
              className="relative group"
            >
              <Link
                to={`/course/${course.id}`}
                className="block"
              >
                <div className="border border-border rounded-lg bg-surface p-6 hover:border-primary transition-all hover:shadow-lg hover:shadow-primary/10">
                  <div className="flex items-start justify-between mb-3">
                    <h3 className="text-xl font-bold text-primary group-hover:text-primary/90 line-clamp-1">
                      {course.title}
                    </h3>
                    {getStatusBadge(course.status)}
                  </div>
                
                <p className="text-gray-400 text-sm mb-4 line-clamp-2 min-h-[2.5rem]">
                  {course.description}
                </p>
                
                <div className="flex items-center gap-3 text-xs text-gray-500 mb-4">
                  <span className="flex items-center gap-1">
                    <span>📑</span> {course.topics} topics
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <span>⚔️</span> {course.challenges} challenges
                  </span>
                  <span>•</span>
                  <span className="flex items-center gap-1">
                    <span>⏱️</span> {course.estimatedTime}
                  </span>
                </div>
                
                <ProgressBar value={course.progress} max={100} />
                <div className="text-right text-xs text-gray-500 mt-1">
                  {course.progress}% complete
                </div>
              </div>
              </Link>
              
              <button
                onClick={(e) => handleDeleteCourse(e, course.id, course.title)}
                disabled={deletingId === course.id}
                className="absolute top-2 right-2 p-2 text-gray-500 hover:text-error opacity-0 group-hover:opacity-100 transition-all"
                title="Delete course"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Activity */}
      {activity.length > 0 && (
        <div>
          <h2 className="text-2xl font-bold text-primary mb-4 flex items-center gap-2">
            <span>📊</span>
            Recent Activity
          </h2>
          <div className="border border-border rounded-lg bg-surface overflow-hidden">
            <div className="divide-y divide-border">
              {activity.map((item) => (
                <div key={item.id} className="p-4 hover:bg-surface/50 transition-colors flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="text-xl">
                      {getActivityStatusIcon(item.status)}
                    </div>
                    <div>
                      <div className="font-semibold text-gray-200">{item.challengeName}</div>
                      <div className="text-sm text-gray-500">{item.courseName}</div>
                    </div>
                  </div>
                  <div className="text-sm text-gray-500">
                    {formatTimeAgo(item.timestamp)}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
