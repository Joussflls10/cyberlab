import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCourses, getStats, deleteCourse } from '../api/client'
import {
  Trash2,
  Search,
  SlidersHorizontal,
  ArrowDownAZ,
  LayoutGrid,
  List,
  CheckSquare,
  Square,
  X,
  AlertTriangle,
  Sparkles,
} from 'lucide-react'
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

interface DeleteDialogState {
  open: boolean
  ids: string[]
  label: string
}

type SortKey = 'title' | 'progress' | 'challenges' | 'topics'
type ViewMode = 'grid' | 'list'
type StatusFilter = 'all' | 'completed' | 'in-progress' | 'not-started'

export default function Home() {
  const [courses, setCourses] = useState<Course[]>([])
  const [stats, setStats] = useState<Stats | null>(null)
  const [activity, setActivity] = useState<Activity[]>([])
  const [loading, setLoading] = useState(true)
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set())
  const [manageMode, setManageMode] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [sortBy, setSortBy] = useState<SortKey>('title')
  const [viewMode, setViewMode] = useState<ViewMode>('grid')
  const [deleteDialog, setDeleteDialog] = useState<DeleteDialogState>({ open: false, ids: [], label: '' })
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null)

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
        topics: course.topic_count ?? course.topics ?? 0,
        challenges: course.challenge_count ?? course.challenges ?? 0,
        progress: course.progress ?? 0,
        estimatedTime: course.estimatedTime || `${Math.ceil(((course.challenge_count ?? course.challenges ?? 0) || 0) * 15)} min`,
        status: (course.progress ?? 0) === 100 ? 'completed' : (course.progress ?? 0) > 0 ? 'in-progress' : 'not-started'
      }))
      
      setCourses(mappedCourses)
      setSelectedIds(prev => {
        const available = new Set(mappedCourses.map(c => c.id))
        return new Set([...prev].filter(id => available.has(id)))
      })
      
      // Map stats
      setStats({
        totalCourses: statsData?.totalCourses ?? statsData?.courses_completed ?? mappedCourses.length,
        completedChallenges: statsData?.completedChallenges ?? statsData?.challenges_completed ?? 0,
        currentStreak: statsData?.currentStreak ?? statsData?.current_streak ?? 0
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

  const openDeleteDialog = (ids: string[], label: string) => {
    if (ids.length === 0) return
    setDeleteDialog({ open: true, ids, label })
  }

  const handleDeleteCourseClick = (e: React.MouseEvent, courseId: string, courseTitle: string) => {
    e.preventDefault()
    e.stopPropagation()

    openDeleteDialog([courseId], `Delete course “${courseTitle}”`)
  }

  const performDelete = async () => {
    const ids = [...new Set(deleteDialog.ids)]
    if (ids.length === 0) {
      setDeleteDialog({ open: false, ids: [], label: '' })
      return
    }

    setDeletingIds(new Set(ids))

    try {
      const results = await Promise.all(
        ids.map(async (id) => {
          try {
            const result = await deleteCourse(id)
            return {
              id,
              success: result?.success !== false,
              message: result?.message || 'Deleted',
            }
          } catch (error) {
            const message = error instanceof Error ? error.message : 'Unknown delete error'
            return { id, success: false, message }
          }
        })
      )

      const deletedIds = results.filter(r => r.success).map(r => r.id)
      const failed = results.filter(r => !r.success)

      if (deletedIds.length > 0) {
        setCourses(prev => prev.filter(course => !deletedIds.includes(course.id)))
        setSelectedIds(prev => {
          const next = new Set(prev)
          deletedIds.forEach(id => next.delete(id))
          return next
        })
      }

      if (failed.length === 0) {
        setFeedback({
          type: 'success',
          message: deletedIds.length === 1
            ? 'Course deleted successfully.'
            : `${deletedIds.length} courses deleted successfully.`,
        })
      } else {
        const firstError = failed[0]?.message ? ` ${failed[0].message}` : ''
        setFeedback({
          type: 'error',
          message: `Deleted ${deletedIds.length}, failed ${failed.length}.${firstError}`,
        })
      }
    } catch (error) {
      console.error('Failed to delete course:', error)
      setFeedback({ type: 'error', message: 'Failed to delete selected course(s).' })
    } finally {
      setDeletingIds(new Set())
      setDeleteDialog({ open: false, ids: [], label: '' })
    }
  }

  const toggleSelectCourse = (id: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  useEffect(() => {
    loadData()
    
    // Poll for new courses every 5 seconds
    const pollInterval = setInterval(loadData, 5000)
    
    return () => clearInterval(pollInterval)
  }, [])

  useEffect(() => {
    if (!feedback) return
    const timer = setTimeout(() => setFeedback(null), 3500)
    return () => clearTimeout(timer)
  }, [feedback])

  const filteredCourses = useMemo(() => {
    const normalizedSearch = searchQuery.trim().toLowerCase()

    let data = courses.filter(course => {
      const matchesSearch = !normalizedSearch ||
        course.title.toLowerCase().includes(normalizedSearch) ||
        course.description.toLowerCase().includes(normalizedSearch)

      const matchesStatus = statusFilter === 'all' || course.status === statusFilter

      return matchesSearch && matchesStatus
    })

    data = [...data].sort((a, b) => {
      switch (sortBy) {
        case 'progress':
          return b.progress - a.progress || a.title.localeCompare(b.title)
        case 'challenges':
          return b.challenges - a.challenges || a.title.localeCompare(b.title)
        case 'topics':
          return b.topics - a.topics || a.title.localeCompare(b.title)
        case 'title':
        default:
          return a.title.localeCompare(b.title)
      }
    })

    return data
  }, [courses, searchQuery, statusFilter, sortBy])

  const selectedCount = selectedIds.size
  const allVisibleSelected = filteredCourses.length > 0 && filteredCourses.every(course => selectedIds.has(course.id))

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
            <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
              <span className="text-4xl">💀</span>
              <div>
                <h1 className="text-4xl font-bold text-primary">CyberLab</h1>
                <p className="text-gray-400 text-sm">Terminal-Based Security Training Platform</p>
              </div>
            </div>
            
            <div className="flex flex-col sm:flex-row sm:items-center gap-6 mt-6">
              <Link
                to="/grinder"
                className="inline-flex items-center gap-2 px-6 py-3 bg-primary/20 hover:bg-primary/30 border border-primary text-primary font-bold rounded transition-all hover:scale-105"
              >
                <span>📤</span>
                Upload Document
              </Link>
              
              <div className="flex flex-wrap gap-4 sm:gap-6 text-sm">
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
      {feedback && (
        <div
          className={`rounded-lg border px-4 py-3 text-sm ${
            feedback.type === 'success'
              ? 'border-primary/40 bg-primary/10 text-primary'
              : 'border-error/40 bg-error/10 text-error'
          }`}
        >
          {feedback.message}
        </div>
      )}

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
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4">
            <span className="text-4xl">💀</span>
            <div>
              <h1 className="text-4xl font-bold text-primary">CyberLab</h1>
              <p className="text-gray-400 text-sm">Terminal-Based Security Training Platform</p>
            </div>
          </div>
          
          <div className="flex flex-col sm:flex-row sm:items-center gap-6 mt-6">
            <Link
              to="/grinder"
              className="inline-flex items-center gap-2 px-6 py-3 bg-primary/20 hover:bg-primary/30 border border-primary text-primary font-bold rounded transition-all hover:scale-105"
            >
              <Sparkles className="w-4 h-4" />
              Upload Document
            </Link>
            
            {stats && (
              <div className="flex flex-wrap gap-4 sm:gap-6 text-sm">
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

      {/* Course controls */}
      <div className="border border-border rounded-lg bg-surface/70 p-4 space-y-4">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <h2 className="text-lg font-bold text-gray-100">Course Manager</h2>
            <p className="text-sm text-gray-500">
              {filteredCourses.length} visible of {courses.length} total course{courses.length === 1 ? '' : 's'}
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <button
              onClick={() => {
                setManageMode(prev => !prev)
                if (manageMode) setSelectedIds(new Set())
              }}
              className={`inline-flex items-center gap-2 px-3 py-2 rounded border text-sm transition-colors ${
                manageMode
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-gray-300 hover:border-primary/40 hover:text-primary'
              }`}
            >
              <SlidersHorizontal className="w-4 h-4" />
              {manageMode ? 'Exit Manage Mode' : 'Manage Courses'}
            </button>

            {manageMode && (
              <>
                <button
                  onClick={() => {
                    if (allVisibleSelected) {
                      setSelectedIds(new Set())
                    } else {
                      setSelectedIds(new Set(filteredCourses.map(c => c.id)))
                    }
                  }}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded border border-border text-sm text-gray-300 hover:border-primary/40 hover:text-primary transition-colors"
                >
                  {allVisibleSelected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                  {allVisibleSelected ? 'Unselect Visible' : 'Select Visible'}
                </button>

                <button
                  onClick={() => openDeleteDialog([...selectedIds], `Delete ${selectedCount} selected course${selectedCount === 1 ? '' : 's'}`)}
                  disabled={selectedCount === 0 || deletingIds.size > 0}
                  className="inline-flex items-center gap-2 px-3 py-2 rounded border border-error/40 bg-error/10 text-sm text-error disabled:opacity-50 disabled:cursor-not-allowed hover:bg-error/20 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                  Delete Selected ({selectedCount})
                </button>
              </>
            )}
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <label className="relative md:col-span-2">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search courses by title or description"
              className="w-full bg-background border border-border rounded pl-9 pr-3 py-2 text-sm text-gray-200 placeholder:text-gray-500 focus:outline-none focus:border-primary/50"
            />
          </label>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            className="bg-background border border-border rounded px-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-primary/50"
          >
            <option value="all">All statuses</option>
            <option value="not-started">Not started</option>
            <option value="in-progress">In progress</option>
            <option value="completed">Completed</option>
          </select>

          <div className="flex gap-2">
            <label className="flex-1 relative">
              <ArrowDownAZ className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
              <select
                value={sortBy}
                onChange={(e) => setSortBy(e.target.value as SortKey)}
                className="w-full bg-background border border-border rounded pl-9 pr-3 py-2 text-sm text-gray-200 focus:outline-none focus:border-primary/50"
              >
                <option value="title">Sort: Title</option>
                <option value="progress">Sort: Progress</option>
                <option value="challenges">Sort: Challenges</option>
                <option value="topics">Sort: Topics</option>
              </select>
            </label>

            <div className="inline-flex border border-border rounded overflow-hidden">
              <button
                onClick={() => setViewMode('grid')}
                className={`px-3 py-2 ${viewMode === 'grid' ? 'bg-primary/10 text-primary' : 'text-gray-400 hover:text-gray-200'}`}
                title="Grid view"
              >
                <LayoutGrid className="w-4 h-4" />
              </button>
              <button
                onClick={() => setViewMode('list')}
                className={`px-3 py-2 border-l border-border ${viewMode === 'list' ? 'bg-primary/10 text-primary' : 'text-gray-400 hover:text-gray-200'}`}
                title="List view"
              >
                <List className="w-4 h-4" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Course Grid */}
      <div>
        <h2 className="text-2xl font-bold text-primary mb-4 flex items-center gap-2">
          <span>📖</span>
          Available Courses {manageMode && <span className="text-sm text-gray-500 font-normal">(Manage mode active)</span>}
        </h2>

        {filteredCourses.length === 0 ? (
          <div className="border border-border rounded-lg bg-surface/60 p-8 text-center">
            <div className="mx-auto mb-3 w-12 h-12 rounded-full bg-surface border border-border flex items-center justify-center text-gray-500">
              <Search className="w-5 h-5" />
            </div>
            <h3 className="text-gray-200 font-semibold">No courses match your filters</h3>
            <p className="text-sm text-gray-500 mt-1">Try clearing search or changing status/sort options.</p>
          </div>
        ) : (
          <div className={`${viewMode === 'grid' ? 'grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6' : 'space-y-4'}`}>
            {filteredCourses.map((course) => {
              const selected = selectedIds.has(course.id)
              const deleting = deletingIds.has(course.id)

              const content = (
                <div
                  className={`border rounded-lg bg-surface p-6 transition-all ${
                    selected
                      ? 'border-primary shadow-lg shadow-primary/10'
                      : 'border-border hover:border-primary/60'
                  } ${viewMode === 'list' ? 'flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4' : ''}`}
                >
                  <div className={viewMode === 'list' ? 'flex-1 min-w-0' : ''}>
                    <div className="flex items-start justify-between mb-3 gap-2">
                      <h3 className="text-xl font-bold text-primary line-clamp-1">{course.title}</h3>
                      {getStatusBadge(course.status)}
                    </div>

                    <p className="text-gray-400 text-sm mb-4 line-clamp-2 min-h-[2.5rem]">
                      {course.description}
                    </p>

                    <div className="flex flex-wrap items-center gap-3 text-xs text-gray-500 mb-4">
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

                  {manageMode && (
                    <div className="flex items-center gap-2">
                      <button
                        onClick={(e) => {
                          e.preventDefault()
                          e.stopPropagation()
                          toggleSelectCourse(course.id)
                        }}
                        className={`inline-flex items-center gap-2 px-3 py-2 rounded border text-sm ${
                          selected
                            ? 'border-primary bg-primary/10 text-primary'
                            : 'border-border text-gray-300 hover:border-primary/40 hover:text-primary'
                        }`}
                      >
                        {selected ? <CheckSquare className="w-4 h-4" /> : <Square className="w-4 h-4" />}
                        {selected ? 'Selected' : 'Select'}
                      </button>
                    </div>
                  )}
                </div>
              )

              return (
                <div key={course.id} className="relative group">
                  {manageMode ? (
                    <div onClick={() => toggleSelectCourse(course.id)} className="cursor-pointer">
                      {content}
                    </div>
                  ) : (
                    <Link to={`/course/${course.id}`} className="block">
                      {content}
                    </Link>
                  )}

                  <button
                    onClick={(e) => handleDeleteCourseClick(e, course.id, course.title)}
                    disabled={deleting}
                    className="absolute top-2 right-2 p-2 text-gray-500 hover:text-error opacity-0 group-hover:opacity-100 transition-all disabled:opacity-50"
                    title="Delete course"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              )
            })}
          </div>
        )}
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

      {/* Delete confirmation modal */}
      {deleteDialog.open && (
        <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="w-full max-w-md border border-border rounded-lg bg-surface p-6 shadow-2xl">
            <div className="flex items-start justify-between gap-3 mb-4">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-error/20 border border-error/30 flex items-center justify-center text-error">
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-gray-100">Confirm Deletion</h3>
                  <p className="text-sm text-gray-500">This action cannot be undone.</p>
                </div>
              </div>

              <button
                onClick={() => setDeleteDialog({ open: false, ids: [], label: '' })}
                className="text-gray-500 hover:text-gray-300"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <p className="text-sm text-gray-300 mb-5">{deleteDialog.label}</p>

            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteDialog({ open: false, ids: [], label: '' })}
                className="px-4 py-2 border border-border rounded text-sm text-gray-300 hover:border-primary/40 hover:text-primary transition-colors"
                disabled={deletingIds.size > 0}
              >
                Cancel
              </button>
              <button
                onClick={performDelete}
                className="px-4 py-2 border border-error/40 bg-error/10 rounded text-sm text-error hover:bg-error/20 transition-colors disabled:opacity-50"
                disabled={deletingIds.size > 0}
              >
                {deletingIds.size > 0 ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
