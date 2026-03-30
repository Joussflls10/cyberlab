import { useState, useRef, useEffect, useMemo } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  Sparkles,
  FileUp,
  FileText,
  BrainCircuit,
  Hammer,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Rocket,
  Clock3,
  TerminalSquare,
  XCircle,
} from 'lucide-react'
import { createImportJob, getJobStatus, getJobLogs, getCourse, getTopics, cancelJob } from '../api/client'

interface GrinderStatus {
  job_id: string
  status: 'pending' | 'processing' | 'completed' | 'error'
  raw_progress: number
  progress: {
    topic_extraction: number
    challenge_generation: number
  }
  topics?: {
    id: string
    title: string
    challenges: number
  }[]
  course?: {
    id: string
    title: string
    description: string
  }
  error?: string
}

interface LogEntry {
  timestamp: string
  message: string
  level: 'info' | 'warn' | 'error'
}

interface ErrorGuidance {
  headline: string
  checks: string[]
  suggestedDelaySeconds: number
  showDelayedRetry: boolean
}

type View = 'upload' | 'processing' | 'results' | 'error'

const MAX_UPLOAD_MB = 50

function normalizeLogs(logText: string): string {
  if (!logText) return ''

  const trimmed = logText.trim()
  if (trimmed.startsWith('"') && trimmed.endsWith('"')) {
    try {
      const parsed = JSON.parse(trimmed)
      if (typeof parsed === 'string') return parsed
    } catch {
      // keep original
    }
  }

  return logText
}

function getErrorGuidance(message: string): ErrorGuidance {
  const text = (message || '').toLowerCase()
  const isRateLimited = /429|too many requests|rate-limit|rate limited|temporarily rate-limited/.test(text)
  const isNoPublishable = text.includes('no publishable topics remained')
  const isNoTopics = text.includes('no topics were extracted') || text.includes('course has no topics')

  if (isNoPublishable) {
    return {
      headline: 'Generation paused to protect challenge quality',
      checks: [
        'The pipeline rejected low-quality output after filtering.',
        'This commonly happens when the AI provider is rate-limited.',
        'Wait briefly, then retry (the backend now avoids publishing empty courses).',
      ],
      suggestedDelaySeconds: 90,
      showDelayedRetry: true,
    }
  }

  if (isRateLimited) {
    return {
      headline: 'AI provider is temporarily rate-limited',
      checks: [
        'Your document upload was received correctly.',
        'The provider returned temporary rate-limit responses (429).',
        'Retry after ~90 seconds for the best chance of success.',
      ],
      suggestedDelaySeconds: 90,
      showDelayedRetry: true,
    }
  }

  if (isNoTopics) {
    return {
      headline: 'Could not extract enough topics from this file',
      checks: [
        'Confirm the document is readable and contains sectioned content.',
        'Try again after a short delay if AI services are unstable.',
        'Use the logs panel to inspect extraction chunk stats.',
      ],
      suggestedDelaySeconds: 45,
      showDelayedRetry: true,
    }
  }

  return {
    headline: 'Could not finish course generation',
    checks: [
      'Make sure the file is a valid PDF or PPTX.',
      `Keep upload size under ${MAX_UPLOAD_MB}MB.`,
      'Confirm backend and AI provider connectivity.',
      'Retry once after a short delay if rate-limited.',
    ],
    suggestedDelaySeconds: 30,
    showDelayedRetry: false,
  }
}

export default function Grinder() {
  const navigate = useNavigate()
  const [view, setView] = useState<View>('upload')
  const [isDragging, setIsDragging] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [status, setStatus] = useState<GrinderStatus | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [error, setError] = useState<string>('')
  const [delayedRetrySeconds, setDelayedRetrySeconds] = useState<number | null>(null)
  const [selectedFileName, setSelectedFileName] = useState<string>('')
  const [startedAt, setStartedAt] = useState<number | null>(null)
  const [isCancelling, setIsCancelling] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

  const elapsedSeconds = useMemo(() => {
    if (!startedAt) return 0
    return Math.max(0, Math.floor((Date.now() - startedAt) / 1000))
  }, [startedAt, logs.length, status?.raw_progress])

  const prettyElapsed = useMemo(() => {
    const m = Math.floor(elapsedSeconds / 60)
    const s = elapsedSeconds % 60
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`
  }, [elapsedSeconds])

  const errorGuidance = useMemo(() => getErrorGuidance(error), [error])

  // Auto-scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Poll status and logs when processing
  useEffect(() => {
    if (view !== 'processing' || !status?.job_id) return

    let isPolling = true
    
    const pollStatus = async () => {
      if (!isPolling) return
      
      try {
        const jobStatus = await getJobStatus(status.job_id)
        
        // Calculate progress for display
        // Backend sends 0-100, we map to our UI segments
        const backendProgress = jobStatus.progress_percent
        let topicExtractionProgress = 0
        let challengeGenerationProgress = 0
        
        if (backendProgress <= 40) {
          // Topic extraction phase (0-40% maps to 0-100% of topic extraction)
          topicExtractionProgress = (backendProgress / 40) * 100
          challengeGenerationProgress = 0
        } else {
          // Challenge generation phase
          topicExtractionProgress = 100
          challengeGenerationProgress = ((backendProgress - 40) / 60) * 100
        }
        
        setStatus(prev => ({
          ...prev!,
          status: jobStatus.status as GrinderStatus['status'],
          raw_progress: backendProgress,
          progress: {
            topic_extraction: topicExtractionProgress,
            challenge_generation: challengeGenerationProgress
          },
          course: jobStatus.course_id ? {
            id: jobStatus.course_id,
            title: 'Generated Course',
            description: `${jobStatus.topics_count} topics, ${jobStatus.challenges_count} challenges`
          } : prev?.course,
          error: jobStatus.error_message || undefined
        }))

        if (jobStatus.status === 'completed') {
          isPolling = false
          // Fetch course details including topics
          if (jobStatus.course_id) {
            try {
              const [courseData, topicData] = await Promise.all([
                getCourse(jobStatus.course_id),
                getTopics(jobStatus.course_id),
              ])
              
              // Validate course has content
              if (!Array.isArray(topicData) || topicData.length === 0) {
                throw new Error('Course has no topics - processing may have failed')
              }
              
              setStatus(prev => ({
                ...prev!,
                course: {
                  id: jobStatus.course_id!,
                  title: courseData.title,
                  description: `${jobStatus.topics_count} topics, ${jobStatus.challenges_count} challenges`
                },
                topics: topicData.map((t: any) => ({
                  id: t.id,
                  title: t.name || t.title || 'Topic',
                  challenges: t.challenge_count ?? t.challenges ?? 0,
                }))
              }))
              setView('results')
            } catch (err) {
              console.error('Failed to fetch course details:', err)
              setError(err instanceof Error ? err.message : 'Failed to load course data')
              setView('error')
            }
          } else {
            setError('No course ID returned from job')
            setView('error')
          }
        } else if (jobStatus.status === 'error') {
          isPolling = false
          setError(jobStatus.error_message || 'Unknown error occurred')
          setView('error')
        }
      } catch (err) {
        console.error('Failed to poll status:', err)
      }
    }

    const pollLogs = async () => {
      if (!isPolling) return
      
      try {
        const logText = await getJobLogs(status.job_id)
        const normalizedLogText = normalizeLogs(logText)
        const newLogs = normalizedLogText.split('\n').filter(Boolean).map(line => {
          const match = line.match(/\[([^\]]+)\]\s*\[(\w+)\]\s*(.*)/)
          if (match) {
            return {
              timestamp: match[1],
              level: match[2].toLowerCase() as 'info' | 'warn' | 'error',
              message: match[3]
            }
          }
          return {
            timestamp: new Date().toISOString(),
            level: 'info' as const,
            message: line
          }
        })
        setLogs(newLogs)
      } catch (err) {
        console.error('Failed to fetch logs:', err)
      }
    }

    // Initial polls
    pollStatus()
    pollLogs()
    
    // Set up intervals
    const statusInterval = setInterval(pollStatus, 1000)
    const logInterval = setInterval(pollLogs, 500)

    return () => {
      isPolling = false
      clearInterval(statusInterval)
      clearInterval(logInterval)
    }
  }, [view, status?.job_id])

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    setIsDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) handleFile(file)
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }

  const handleFile = async (file: File) => {
    const fileName = file.name || 'uploaded-file'
    const ext = fileName.includes('.') ? fileName.slice(fileName.lastIndexOf('.')).toLowerCase() : ''
    if (!['.pdf', '.pptx'].includes(ext)) {
      setError('Only PDF and PPTX files are supported.')
      setView('error')
      return
    }

    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      setError(`File is too large. Maximum allowed size is ${MAX_UPLOAD_MB}MB.`)
      setView('error')
      return
    }

    setView('processing')
    setUploadProgress(0)
    setLogs([])
    setError('')
    setSelectedFileName(fileName)
    setStartedAt(Date.now())

    let progressInterval: ReturnType<typeof setInterval> | null = null

    try {
      // Simulate upload progress
      progressInterval = setInterval(() => {
        setUploadProgress(prev => Math.min(prev + 10, 90))
      }, 200)

      // Create async job
      const result = await createImportJob(file)
      
      if (progressInterval) clearInterval(progressInterval)
      setUploadProgress(100)

      if (result.success && result.legacy && result.course_id) {
        try {
          const [courseData, topicData] = await Promise.all([
            getCourse(result.course_id),
            getTopics(result.course_id),
          ])

          const topics = Array.isArray(topicData)
            ? topicData.map((t: any) => ({
                id: t.id,
                title: t.name || t.title || 'Topic',
                challenges: t.challenge_count ?? t.challenges ?? 0,
              }))
            : []

          setStatus({
            job_id: 'legacy-upload',
            status: 'completed',
            raw_progress: 100,
            progress: {
              topic_extraction: 100,
              challenge_generation: 100,
            },
            course: {
              id: result.course_id,
              title: courseData?.title || 'Generated Course',
              description: `${result.topics_count ?? topics.length ?? 0} topics, ${result.challenges_count ?? 0} challenges`,
            },
            topics,
          })
          setView('results')
          return
        } catch (err) {
          console.error('Legacy course fetch failed:', err)
          setStatus({
            job_id: 'legacy-upload',
            status: 'completed',
            raw_progress: 100,
            progress: {
              topic_extraction: 100,
              challenge_generation: 100,
            },
            course: {
              id: result.course_id,
              title: 'Generated Course',
              description: `${result.topics_count ?? 0} topics, ${result.challenges_count ?? 0} challenges`,
            },
          })
          setView('results')
          return
        }
      }

      if (result.success && result.job_id) {
        setStatus({
          job_id: result.job_id,
          status: 'pending',
          raw_progress: 0,
          progress: {
            topic_extraction: 0,
            challenge_generation: 0
          }
        })
      } else {
        setError(result.message || 'Failed to create import job')
        setView('error')
      }
    } catch (err) {
      if (progressInterval) clearInterval(progressInterval)
      setError(err instanceof Error ? err.message : 'Upload failed')
      setView('error')
    }
  }

  const handleRetry = () => {
    setView('upload')
    setStatus(null)
    setLogs([])
    setError('')
    setUploadProgress(0)
    setSelectedFileName('')
    setStartedAt(null)
    setIsCancelling(false)
    setDelayedRetrySeconds(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  useEffect(() => {
    if (view !== 'error') {
      if (delayedRetrySeconds !== null) setDelayedRetrySeconds(null)
      return
    }

    if (delayedRetrySeconds === null) return
    if (delayedRetrySeconds <= 0) {
      handleRetry()
      return
    }

    const timer = setTimeout(() => {
      setDelayedRetrySeconds(prev => (prev === null ? null : prev - 1))
    }, 1000)

    return () => clearTimeout(timer)
  }, [view, delayedRetrySeconds])

  const handleCancel = async () => {
    if (!status?.job_id || isCancelling) return

    setIsCancelling(true)
    try {
      const response = await cancelJob(status.job_id)
      if (!response.success) {
        setError(response.message || 'Could not cancel grinder job')
        setView('error')
        return
      }

      setError('Job cancelled by user.')
      setView('error')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to cancel job')
      setView('error')
    } finally {
      setIsCancelling(false)
    }
  }

  const handleGoToCourse = () => {
    if (status?.course?.id) {
      navigate(`/course/${status.course.id}`)
    }
  }

  const overallProgress = status?.raw_progress ?? 0

  const pipelineSteps = [
    {
      id: 'upload',
      icon: FileUp,
      title: 'Upload',
      description: selectedFileName || 'Waiting for file',
      complete: uploadProgress >= 100,
      active: uploadProgress < 100,
    },
    {
      id: 'topics',
      icon: BrainCircuit,
      title: 'Topic Extraction',
      description: `${Math.round(status?.progress.topic_extraction ?? 0)}%`,
      complete: (status?.raw_progress ?? 0) >= 40,
      active: (status?.raw_progress ?? 0) >= 15 && (status?.raw_progress ?? 0) < 40,
    },
    {
      id: 'challenges',
      icon: Hammer,
      title: 'Challenge Generation',
      description: `${Math.round(status?.progress.challenge_generation ?? 0)}%`,
      complete: (status?.raw_progress ?? 0) >= 90,
      active: (status?.raw_progress ?? 0) >= 40 && (status?.raw_progress ?? 0) < 90,
    },
    {
      id: 'finalize',
      icon: CheckCircle2,
      title: 'Finalize Course',
      description: status?.status === 'completed' ? 'Done' : 'Pending',
      complete: status?.status === 'completed',
      active: (status?.raw_progress ?? 0) >= 90 && status?.status !== 'completed',
    },
  ]

  // Upload View
  if (view === 'upload') {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <section className="rounded-2xl border border-border bg-gradient-to-r from-primary/10 via-secondary/5 to-surface p-6 sm:p-8">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-3 py-1 text-xs text-primary">
                <Sparkles className="h-3.5 w-3.5" />
                AI Course Generator
              </div>
              <h2 className="text-3xl font-bold text-white sm:text-4xl">Grinder Studio</h2>
              <p className="mt-2 max-w-2xl text-sm text-gray-300 sm:text-base">
                Drop in one PDF or PPTX and automatically convert it into a structured course with topics, lab-ready challenges,
                and progress tracking.
              </p>
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs sm:text-sm">
              <div className="rounded-xl border border-border bg-black/25 px-3 py-2 text-gray-300">Max size: <span className="text-primary">50MB</span></div>
              <div className="rounded-xl border border-border bg-black/25 px-3 py-2 text-gray-300">Formats: <span className="text-primary">PDF · PPTX</span></div>
            </div>
          </div>
        </section>

        <section
          className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition-all duration-200 sm:p-14
            ${isDragging
              ? 'border-primary bg-primary/10 shadow-[0_0_0_4px_rgba(0,255,136,0.08)]'
              : 'border-border bg-surface/70 hover:border-primary/60 hover:bg-surface'
            }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.pptx"
            className="hidden"
            onChange={handleFileSelect}
          />

          <div className="mx-auto mb-5 flex h-16 w-16 items-center justify-center rounded-2xl bg-primary/15 text-primary">
            <FileText className="h-8 w-8" />
          </div>
          <h3 className="text-2xl font-semibold text-white">Drop your training document</h3>
          <p className="mt-2 text-sm text-gray-400">or click here to browse your local files</p>
          <p className="mt-4 text-xs text-gray-500">Tip: technical guides with procedural steps produce the best challenge quality.</p>
        </section>

        <section className="grid gap-4 md:grid-cols-3">
          {[
            { icon: BrainCircuit, title: 'Analyze', description: 'Extracts topics, commands, and procedural knowledge from your document.' },
            { icon: Hammer, title: 'Generate', description: 'Builds hands-on command/file/output challenges with validation scripts.' },
            { icon: Rocket, title: 'Launch', description: 'Publishes a course immediately to your CyberLab catalog.' },
          ].map((item) => (
            <div key={item.title} className="rounded-xl border border-border bg-surface/70 p-4">
              <item.icon className="mb-3 h-5 w-5 text-primary" />
              <h4 className="text-sm font-semibold text-white">{item.title}</h4>
              <p className="mt-1 text-xs text-gray-400">{item.description}</p>
            </div>
          ))}
        </section>
      </div>
    )
  }

  // Processing View
  if (view === 'processing') {
    return (
      <div className="mx-auto max-w-7xl space-y-6">
        <section className="rounded-2xl border border-border bg-surface/70 p-5 sm:p-6">
          <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <h2 className="text-2xl font-semibold text-white sm:text-3xl">Building your course…</h2>
              <p className="mt-1 text-sm text-gray-400">{selectedFileName || 'Uploaded file'} is being transformed into structured labs.</p>
            </div>
            <div className="flex items-center gap-3">
              <div className="rounded-lg border border-border bg-black/20 px-3 py-2 text-xs text-gray-300">
                <Clock3 className="mr-1 inline h-3.5 w-3.5" />
                Elapsed: <span className="text-primary">{prettyElapsed}</span>
              </div>
              <button
                onClick={handleCancel}
                disabled={isCancelling}
                className="inline-flex items-center gap-2 rounded-lg border border-error/40 bg-error/10 px-3 py-2 text-xs text-error transition hover:bg-error/20 disabled:opacity-60"
              >
                <XCircle className="h-3.5 w-3.5" />
                {isCancelling ? 'Cancelling…' : 'Cancel'}
              </button>
            </div>
          </div>

          <div className="mb-2 flex items-center justify-between text-xs text-gray-400">
            <span>Overall progress</span>
            <span className="text-primary">{overallProgress}%</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full border border-border bg-background">
            <div className="h-full bg-gradient-to-r from-primary to-secondary transition-all duration-300" style={{ width: `${overallProgress}%` }} />
          </div>
        </section>

        <section className="grid gap-6 lg:grid-cols-[1.1fr_1fr]">
          <div className="space-y-4 rounded-2xl border border-border bg-surface/70 p-5">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-400">Pipeline Stages</h3>
            <div className="space-y-3">
              {pipelineSteps.map((step) => {
                const Icon = step.icon
                return (
                  <div
                    key={step.id}
                    className={`flex items-center justify-between rounded-xl border px-4 py-3 transition ${
                      step.complete
                        ? 'border-primary/40 bg-primary/10'
                        : step.active
                          ? 'border-secondary/40 bg-secondary/10'
                          : 'border-border bg-black/20'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`flex h-9 w-9 items-center justify-center rounded-lg ${
                          step.complete ? 'bg-primary/20 text-primary' : step.active ? 'bg-secondary/20 text-secondary' : 'bg-surface text-gray-500'
                        }`}
                      >
                        <Icon className="h-4 w-4" />
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white">{step.title}</p>
                        <p className="text-xs text-gray-400">{step.description}</p>
                      </div>
                    </div>
                    {step.complete ? <CheckCircle2 className="h-5 w-5 text-primary" /> : step.active ? <RefreshCw className="h-4 w-4 animate-spin text-secondary" /> : null}
                  </div>
                )
              })}
            </div>

            <div className="grid gap-3 sm:grid-cols-2">
              <div className="rounded-xl border border-border bg-black/20 p-3 text-sm text-gray-300">
                Topics extracted
                <div className="mt-1 text-xl font-semibold text-primary">{status?.course ? status?.course.description.split(' ')[0] : (status?.raw_progress ?? 0) >= 40 ? '1+' : '…'}</div>
              </div>
              <div className="rounded-xl border border-border bg-black/20 p-3 text-sm text-gray-300">
                Challenges generated
                <div className="mt-1 text-xl font-semibold text-secondary">{status?.course?.description.match(/\d+\s+challenges?/i)?.[0]?.split(' ')[0] ?? ((status?.raw_progress ?? 0) >= 40 ? '…' : '0')}</div>
              </div>
            </div>
          </div>

          <div className="rounded-2xl border border-border bg-[#060606] p-5">
            <div className="mb-3 flex items-center gap-2 border-b border-border pb-3">
              <TerminalSquare className="h-4 w-4 text-primary" />
              <h3 className="text-sm font-semibold text-gray-300">Live processing logs</h3>
            </div>

            <div className="h-[360px] overflow-y-auto space-y-1 text-xs sm:text-sm">
              {logs.length === 0 ? (
                <div className="mt-6 rounded-lg border border-border bg-black/30 p-4 text-center text-gray-500">Waiting for logs…</div>
              ) : (
                logs.map((log, idx) => (
                  <div key={idx} className="flex gap-2 rounded px-2 py-1 hover:bg-white/5">
                    <span className="shrink-0 text-gray-600">[{log.timestamp.split('T')[1]?.split('.')[0] || '--:--:--'}]</span>
                    <span
                      className={`shrink-0 font-semibold uppercase ${
                        log.level === 'error' ? 'text-error' : log.level === 'warn' ? 'text-secondary' : 'text-primary'
                      }`}
                    >
                      {log.level}
                    </span>
                    <span className="text-gray-300">{log.message}</span>
                  </div>
                ))
              )}
              <div ref={logsEndRef} />
            </div>
          </div>
        </section>
      </div>
    )
  }

  // Results View
  if (view === 'results') {
    return (
      <div className="mx-auto max-w-6xl space-y-6">
        <section className="rounded-2xl border border-primary/30 bg-primary/10 p-6 sm:p-8">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <div className="mb-3 inline-flex items-center gap-2 rounded-full border border-primary/40 bg-primary/15 px-3 py-1 text-xs text-primary">
                <CheckCircle2 className="h-3.5 w-3.5" />
                Course generation completed
              </div>
              <h2 className="text-3xl font-bold text-white">{status?.course?.title || 'Course generated'}</h2>
              <p className="mt-2 text-sm text-gray-300">{status?.course?.description || 'Your content has been transformed into an interactive learning path.'}</p>
            </div>
            <div className="rounded-xl border border-border bg-black/20 px-4 py-3 text-sm text-gray-300">
              <p>Elapsed time</p>
              <p className="text-lg font-semibold text-primary">{prettyElapsed}</p>
            </div>
          </div>
        </section>

        {status?.topics && status.topics.length > 0 && (
          <section className="rounded-2xl border border-border bg-surface/70 p-5 sm:p-6">
            <h3 className="mb-4 text-lg font-semibold text-white">Detected topic map</h3>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {status.topics.map((topic, idx) => (
                <article key={topic.id} className="rounded-xl border border-border bg-black/20 p-4">
                  <div className="mb-2 flex items-center justify-between">
                    <span className="text-xs text-gray-500">Topic {idx + 1}</span>
                    <span className="rounded-full border border-secondary/30 bg-secondary/10 px-2 py-0.5 text-xs text-secondary">
                      {topic.challenges || 0} challenges
                    </span>
                  </div>
                  <h4 className="text-sm font-semibold text-gray-100">{topic.title}</h4>
                </article>
              ))}
            </div>
          </section>
        )}

        <section className="flex flex-wrap gap-3">
          <button
            onClick={handleGoToCourse}
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 font-semibold text-black transition hover:bg-primary/90"
          >
            <Rocket className="h-4 w-4" />
            Open Course
          </button>
          <button
            onClick={handleRetry}
            className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface/60 px-5 py-3 text-gray-200 transition hover:border-primary/40 hover:text-white"
          >
            <RefreshCw className="h-4 w-4" />
            Generate Another
          </button>
          {status?.course?.id && (
            <Link
              to={`/admin/courses/${status.course.id}/challenges`}
              className="inline-flex items-center gap-2 rounded-xl border border-secondary/40 bg-secondary/10 px-5 py-3 text-secondary transition hover:bg-secondary/20"
            >
              Review Challenges
            </Link>
          )}
          {status?.course?.id && (
            <Link
              to="/"
              className="inline-flex items-center rounded-xl border border-border bg-black/10 px-5 py-3 text-sm text-gray-300 transition hover:bg-black/30"
            >
              Back to Catalog
            </Link>
          )}
        </section>
      </div>
    )
  }

  // Error View
  if (view === 'error') {
    return (
      <div className="mx-auto max-w-3xl">
        <section className="rounded-2xl border border-error/40 bg-error/10 p-6 sm:p-8">
          <div className="mb-4 inline-flex items-center gap-2 rounded-full border border-error/50 bg-error/15 px-3 py-1 text-xs text-error">
            <AlertTriangle className="h-3.5 w-3.5" />
            Processing interrupted
          </div>

          <h2 className="text-2xl font-bold text-white sm:text-3xl">{errorGuidance.headline}</h2>
          <p className="mt-2 text-sm text-gray-300">{error || 'An unknown error occurred while processing your document.'}</p>

          <div className="mt-6 rounded-xl border border-border bg-black/20 p-4">
            <h3 className="mb-2 text-sm font-semibold text-white">Quick checks</h3>
            <ul className="space-y-1 text-sm text-gray-400">
              {errorGuidance.checks.map((item) => (
                <li key={item}>• {item}</li>
              ))}
            </ul>
          </div>

          <div className="mt-6 flex flex-wrap gap-3">
            <button
              onClick={handleRetry}
              className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 font-semibold text-black transition hover:bg-primary/90"
            >
              <RefreshCw className="h-4 w-4" />
              Try Again
            </button>
            {errorGuidance.showDelayedRetry && (
              <button
                onClick={() => setDelayedRetrySeconds(errorGuidance.suggestedDelaySeconds)}
                disabled={delayedRetrySeconds !== null}
                className="inline-flex items-center gap-2 rounded-xl border border-secondary/40 bg-secondary/10 px-5 py-3 font-semibold text-secondary transition hover:bg-secondary/20 disabled:opacity-60 disabled:cursor-not-allowed"
              >
                <Clock3 className="h-4 w-4" />
                {delayedRetrySeconds === null
                  ? `Retry in ${errorGuidance.suggestedDelaySeconds}s`
                  : delayedRetrySeconds > 0
                    ? `Retrying in ${delayedRetrySeconds}s…`
                    : 'Retrying…'}
              </button>
            )}
            <Link
              to="/"
              className="inline-flex items-center gap-2 rounded-xl border border-border bg-surface/70 px-5 py-3 text-gray-200 transition hover:border-primary/40"
            >
              Back to Courses
            </Link>
          </div>
        </section>
      </div>
    )
  }

  // Fallback for any unexpected state
  console.error('Grinder: Unexpected view state:', { view, status, error })
  return (
    <div className="mx-auto max-w-2xl text-center py-12">
      <div className="mb-4 inline-flex h-12 w-12 items-center justify-center rounded-xl bg-error/20 text-error">
        <AlertTriangle className="h-5 w-5" />
      </div>
      <h2 className="text-2xl font-bold text-white">Unexpected UI state</h2>
      <p className="mt-2 text-sm text-gray-400">The page entered an unexpected state. Reset and continue.</p>
      <button
        onClick={handleRetry}
        className="mt-5 inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-3 font-semibold text-black transition hover:bg-primary/90"
      >
        <RefreshCw className="h-4 w-4" />
        Reset Grinder
      </button>
    </div>
  )
}
