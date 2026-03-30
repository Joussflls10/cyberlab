import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { CheckCircle2, ShieldCheck, Trash2, RefreshCw, AlertTriangle } from 'lucide-react'
import {
  getAdminCourseChallenges,
  approveAdminChallenge,
  deleteAdminChallenge,
  hideAllAdminCourseChallenges,
  approveAllAdminCourseChallenges,
  type AdminCourseChallenge,
  bulkSetAdminCourseChallengesActive,
} from '../api/client'

export default function AdminCourseChallenges() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()

  const [loading, setLoading] = useState(true)
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set())
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [courseTitle, setCourseTitle] = useState('Course')
  const [challenges, setChallenges] = useState<AdminCourseChallenge[]>([])
  const [bulkSaving, setBulkSaving] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [sortMode, setSortMode] = useState<'default' | 'quality_desc' | 'quality_asc'>('default')

  const totals = useMemo(() => {
    const active = challenges.filter(c => c.is_active).length
    return {
      total: challenges.length,
      active,
      inactive: challenges.length - active,
    }
  }, [challenges])

  const displayedChallenges = useMemo(() => {
    if (sortMode === 'default') return challenges
    const sorted = [...challenges]
    sorted.sort((a, b) => {
      const qa = a.quality_score ?? 0
      const qb = b.quality_score ?? 0
      return sortMode === 'quality_desc' ? qb - qa : qa - qb
    })
    return sorted
  }, [challenges, sortMode])

  const allVisibleSelected = useMemo(() => {
    if (displayedChallenges.length === 0) return false
    return displayedChallenges.every(c => selectedIds.has(c.id))
  }, [displayedChallenges, selectedIds])

  const selectedCount = selectedIds.size

  const loadData = async () => {
    if (!id) return
    try {
      setLoading(true)
      setError(null)
      setNotice(null)
      const data = await getAdminCourseChallenges(id, true)
      setCourseTitle(data.course.title)
      setChallenges(data.challenges)
      setSelectedIds(new Set())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load challenge curation data')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadData()
  }, [id])

  const withSaving = async (challengeId: string, fn: () => Promise<void>) => {
    setSavingIds(prev => new Set(prev).add(challengeId))
    try {
      await fn()
    } finally {
      setSavingIds(prev => {
        const next = new Set(prev)
        next.delete(challengeId)
        return next
      })
    }
  }

  const handleApprove = async (challengeId: string) => {
    await withSaving(challengeId, async () => {
      await approveAdminChallenge(challengeId)
      setChallenges(prev => prev.map(c => (c.id === challengeId ? { ...c, is_active: true } : c)))
      setSelectedIds(prev => {
        const next = new Set(prev)
        next.delete(challengeId)
        return next
      })
    })
  }

  const handleDeactivate = async (challengeId: string) => {
    await withSaving(challengeId, async () => {
      await deleteAdminChallenge(challengeId)
      setChallenges(prev => prev.map(c => (c.id === challengeId ? { ...c, is_active: false } : c)))
      setSelectedIds(prev => {
        const next = new Set(prev)
        next.delete(challengeId)
        return next
      })
    })
  }

  const toggleSelect = (challengeId: string) => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (next.has(challengeId)) next.delete(challengeId)
      else next.add(challengeId)
      return next
    })
  }

  const toggleSelectAllVisible = () => {
    setSelectedIds(prev => {
      const next = new Set(prev)
      if (allVisibleSelected) {
        displayedChallenges.forEach(ch => next.delete(ch.id))
      } else {
        displayedChallenges.forEach(ch => next.add(ch.id))
      }
      return next
    })
  }

  const handleBulkSetActive = async (isActive: boolean) => {
    if (!id || bulkSaving || selectedIds.size === 0) return

    const targetIds = Array.from(selectedIds)
    setBulkSaving(true)
    setNotice(null)
    setError(null)
    try {
      const res = await bulkSetAdminCourseChallengesActive(id, targetIds, isActive)
      setChallenges(prev =>
        prev.map(c => (targetIds.includes(c.id) ? { ...c, is_active: isActive } : c))
      )
      setSelectedIds(new Set())
      setNotice(`Updated ${res.updated} selected challenge(s).`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to update selected challenges')
    } finally {
      setBulkSaving(false)
    }
  }

  const handleHideAll = async () => {
    if (!id || bulkSaving) return
    setBulkSaving(true)
    setNotice(null)
    setError(null)
    try {
      const res = await hideAllAdminCourseChallenges(id)
      setChallenges(prev => prev.map(c => ({ ...c, is_active: false })))
      setNotice(`Hidden ${res.updated} challenges.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to hide challenges')
    } finally {
      setBulkSaving(false)
    }
  }

  const handleApproveAll = async () => {
    if (!id || bulkSaving) return
    setBulkSaving(true)
    setNotice(null)
    setError(null)
    try {
      const res = await approveAllAdminCourseChallenges(id)
      setChallenges(prev => prev.map(c => ({ ...c, is_active: true })))
      setNotice(`Approved ${res.updated} challenges.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to approve challenges')
    } finally {
      setBulkSaving(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64 text-primary">
        <RefreshCw className="w-5 h-5 mr-2 animate-spin" />
        Loading challenge curation view...
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="rounded-2xl border border-error/40 bg-error/10 p-6">
          <div className="inline-flex items-center gap-2 text-error text-sm mb-2">
            <AlertTriangle className="h-4 w-4" />
            Failed to load curation view
          </div>
          <p className="text-sm text-gray-300">{error}</p>
          <div className="mt-4 flex gap-3">
            <button
              onClick={loadData}
              className="px-4 py-2 rounded border border-border text-gray-200 hover:border-primary/40"
            >
              Retry
            </button>
            <button
              onClick={() => navigate(-1)}
              className="px-4 py-2 rounded bg-primary text-black font-semibold"
            >
              Go Back
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-5">
      <section className="rounded-2xl border border-border bg-surface/70 p-5 sm:p-6">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs text-primary mb-3">
              <ShieldCheck className="h-3.5 w-3.5" />
              Admin Challenge Curation
            </div>
            <h1 className="text-2xl font-bold text-white">{courseTitle}</h1>
            <p className="mt-1 text-sm text-gray-400">
              Review generated challenges before students use them.
            </p>
          </div>

          <div className="grid grid-cols-3 gap-2 text-xs">
            <div className="rounded-lg border border-border bg-black/20 px-3 py-2 text-gray-300">Total <span className="text-white">{totals.total}</span></div>
            <div className="rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-primary">Active <span>{totals.active}</span></div>
            <div className="rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-error">Hidden <span>{totals.inactive}</span></div>
          </div>
        </div>

        <div className="mt-4 flex flex-wrap gap-3">
          {id && (
            <Link
              to={`/course/${id}`}
              className="px-4 py-2 rounded bg-primary text-black font-semibold hover:bg-primary/90"
            >
              Open Course
            </Link>
          )}
          <button
            onClick={loadData}
            className="px-4 py-2 rounded border border-border text-gray-200 hover:border-primary/40 inline-flex items-center gap-2"
          >
            <RefreshCw className="w-4 h-4" />
            Refresh
          </button>
          <button
            onClick={handleHideAll}
            disabled={bulkSaving || totals.active === 0}
            className="px-4 py-2 rounded border border-error/30 bg-error/10 text-error disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Hide All Active
          </button>
          <button
            onClick={handleApproveAll}
            disabled={bulkSaving || totals.inactive === 0}
            className="px-4 py-2 rounded border border-primary/30 bg-primary/10 text-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Approve All Hidden
          </button>
          <button
            onClick={() => handleBulkSetActive(true)}
            disabled={bulkSaving || selectedCount === 0}
            className="px-4 py-2 rounded border border-primary/30 bg-primary/10 text-primary disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Approve Selected ({selectedCount})
          </button>
          <button
            onClick={() => handleBulkSetActive(false)}
            disabled={bulkSaving || selectedCount === 0}
            className="px-4 py-2 rounded border border-error/30 bg-error/10 text-error disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Hide Selected ({selectedCount})
          </button>
          <select
            value={sortMode}
            onChange={(e) => setSortMode(e.target.value as 'default' | 'quality_desc' | 'quality_asc')}
            className="px-3 py-2 rounded border border-border bg-black/20 text-gray-200"
          >
            <option value="default">Sort: Topic order</option>
            <option value="quality_desc">Sort: Quality high → low</option>
            <option value="quality_asc">Sort: Quality low → high</option>
          </select>
        </div>
        {notice && (
          <p className="mt-3 text-xs text-primary">{notice}</p>
        )}
      </section>

      <section className="rounded-2xl border border-border bg-surface/70 p-4 overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr className="text-left text-gray-400 border-b border-border">
              <th className="py-2 pr-3">
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={toggleSelectAllVisible}
                  aria-label="Select all visible challenges"
                />
              </th>
              <th className="py-2 pr-3">Status</th>
              <th className="py-2 pr-3">Topic</th>
              <th className="py-2 pr-3">Type</th>
              <th className="py-2 pr-3">Difficulty</th>
              <th className="py-2 pr-3">Quality</th>
              <th className="py-2 pr-3">Question</th>
              <th className="py-2 pr-3">Actions</th>
            </tr>
          </thead>
          <tbody>
            {displayedChallenges.map((challenge) => {
              const isSaving = savingIds.has(challenge.id)
              const isSelected = selectedIds.has(challenge.id)
              const qualityScore = challenge.quality_score ?? 0
              const qualityFlags = challenge.quality_flags ?? []
              const qualityClass = qualityScore >= 80
                ? 'text-primary border-primary/30 bg-primary/10'
                : qualityScore >= 60
                  ? 'text-amber-300 border-amber-300/30 bg-amber-300/10'
                  : 'text-error border-error/30 bg-error/10'

              return (
                <tr key={challenge.id} className="border-b border-border/60 align-top">
                  <td className="py-3 pr-3">
                    <input
                      type="checkbox"
                      checked={isSelected}
                      onChange={() => toggleSelect(challenge.id)}
                      aria-label={`Select challenge ${challenge.id}`}
                    />
                  </td>
                  <td className="py-3 pr-3">
                    {challenge.is_active ? (
                      <span className="inline-flex items-center gap-1 rounded border border-primary/30 bg-primary/10 px-2 py-0.5 text-xs text-primary">
                        Active
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 rounded border border-error/30 bg-error/10 px-2 py-0.5 text-xs text-error">
                        Hidden
                      </span>
                    )}
                  </td>
                  <td className="py-3 pr-3 text-gray-300 max-w-[240px]">{challenge.topic_name}</td>
                  <td className="py-3 pr-3 text-gray-300">{challenge.type}</td>
                  <td className="py-3 pr-3 text-gray-300">{challenge.difficulty}</td>
                  <td className="py-3 pr-3">
                    <div className={`inline-flex rounded border px-2 py-0.5 text-xs ${qualityClass}`}>
                      {qualityScore.toFixed(1)}
                    </div>
                    {qualityFlags.length > 0 && (
                      <p className="mt-1 text-[11px] text-gray-500">
                        {qualityFlags.join(', ')}
                      </p>
                    )}
                    {typeof challenge.pass_rate === 'number' && (
                      <p className="mt-1 text-[11px] text-gray-500">
                        pass rate: {(challenge.pass_rate * 100).toFixed(0)}% ({challenge.passes ?? 0}/{challenge.attempts ?? 0})
                      </p>
                    )}
                  </td>
                  <td className="py-3 pr-3 text-gray-200 max-w-[560px]">
                    <div className="line-clamp-3">{challenge.question}</div>
                    <p className="text-xs text-gray-500 mt-1">Image: {challenge.sandbox_image}</p>
                  </td>
                  <td className="py-3 pr-3">
                    <div className="flex gap-2">
                      <button
                        disabled={isSaving || challenge.is_active}
                        onClick={() => handleApprove(challenge.id)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded border border-primary/30 text-primary bg-primary/10 disabled:opacity-50"
                        title="Approve / activate"
                      >
                        <CheckCircle2 className="w-4 h-4" />
                        Approve
                      </button>
                      <button
                        disabled={isSaving || !challenge.is_active}
                        onClick={() => handleDeactivate(challenge.id)}
                        className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded border border-error/30 text-error bg-error/10 disabled:opacity-50"
                        title="Hide / remove from student view"
                      >
                        <Trash2 className="w-4 h-4" />
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </section>
    </div>
  )
}
