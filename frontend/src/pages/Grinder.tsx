import { useState, useRef, useEffect } from 'react'
import { createImportJob, getJobStatus, getJobLogs, getCourse } from '../api/client'

interface GrinderStatus {
  job_id: string
  status: 'pending' | 'processing' | 'completed' | 'error'
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

type View = 'upload' | 'processing' | 'results' | 'error'

export default function Grinder() {
  const [view, setView] = useState<View>('upload')
  const [isDragging, setIsDragging] = useState(false)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [status, setStatus] = useState<GrinderStatus | null>(null)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [error, setError] = useState<string>('')
  const fileInputRef = useRef<HTMLInputElement>(null)
  const logsEndRef = useRef<HTMLDivElement>(null)

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
              const courseData = await getCourse(jobStatus.course_id)
              
              // Validate course has content
              if (!courseData.topics || courseData.topics.length === 0) {
                throw new Error('Course has no topics - processing may have failed')
              }
              
              setStatus(prev => ({
                ...prev!,
                course: {
                  id: jobStatus.course_id!,
                  title: courseData.title,
                  description: `${jobStatus.topics_count} topics, ${jobStatus.challenges_count} challenges`
                },
                topics: courseData.topics.map((t: any) => ({
                  id: t.id,
                  title: t.name,
                  challenges: 0 // Will be populated later if needed
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
        const newLogs = logText.split('\n').filter(Boolean).map(line => {
          const match = line.match(/\[(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\]\s*\[(\w+)\]\s*(.*)/)
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
    setView('processing')
    setUploadProgress(0)
    setLogs([])
    setError('')

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

      if (result.success && result.job_id) {
        setStatus({
          job_id: result.job_id,
          status: 'pending',
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
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleGoToCourse = () => {
    if (status?.course?.id) {
      window.location.href = `/course/${status.course.id}`
    }
  }

  // Upload View
  if (view === 'upload') {
    return (
      <div className="max-w-2xl mx-auto">
        <h2 className="text-3xl font-bold text-primary mb-2">Grinder</h2>
        <p className="text-gray-400 mb-8">Upload a document to generate an interactive course</p>

        <div
          className={`border-2 border-dashed rounded-lg p-12 text-center transition-all duration-200 cursor-pointer
            ${isDragging 
              ? 'border-primary bg-primary/10' 
              : 'border-border hover:border-primary/50 hover:bg-surface'
            }`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.doc,.docx,.txt,.md"
            className="hidden"
            onChange={handleFileSelect}
          />
          
          <div className="text-6xl mb-4">📄</div>
          <h3 className="text-xl font-bold text-gray-200 mb-2">
            Drop your document here
          </h3>
          <p className="text-gray-400 mb-4">
            or click to browse
          </p>
          <p className="text-sm text-gray-500">
            Supported: PDF, DOC, DOCX, TXT, MD
          </p>
        </div>

        <div className="mt-8 p-4 bg-surface border border-border rounded-lg">
          <h4 className="text-primary font-bold mb-2">How it works:</h4>
          <ul className="text-gray-400 space-y-1 text-sm">
            <li>1. Upload your technical document or tutorial</li>
            <li>2. AI extracts topics and generates challenges</li>
            <li>3. Get an interactive course with hands-on labs</li>
          </ul>
        </div>
      </div>
    )
  }

  // Processing View
  if (view === 'processing') {
    return (
      <div className="max-w-3xl mx-auto">
        <h2 className="text-3xl font-bold text-primary mb-2">Processing</h2>
        <p className="text-gray-400 mb-8">Generating your course...</p>

        {/* Upload Progress */}
        {uploadProgress < 100 && (
          <div className="mb-6">
            <div className="flex justify-between text-sm mb-2">
              <span className="text-gray-400">Uploading...</span>
              <span className="text-primary">{uploadProgress}%</span>
            </div>
            <div className="w-full bg-background border border-border rounded-full h-2 overflow-hidden">
              <div
                className="h-full bg-primary transition-all duration-200"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {/* Processing Progress */}
        {uploadProgress === 100 && status && (
          <>
            <div className="grid grid-cols-2 gap-4 mb-6">
              <div className="bg-surface border border-border rounded-lg p-4">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-gray-400 text-sm">Topic Extraction</span>
                  <span className="text-primary text-sm">{Math.round(status?.progress?.topic_extraction || 0)}%</span>
                </div>
                <div className="w-full bg-background border border-border rounded-full h-2 overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all duration-300"
                    style={{ width: `${status?.progress?.topic_extraction || 0}%` }}
                  />
                </div>
              </div>

              <div className="bg-surface border border-border rounded-lg p-4">
                <div className="flex justify-between items-center mb-2">
                  <span className="text-gray-400 text-sm">Challenge Generation</span>
                  <span className="text-secondary text-sm">{Math.round(status?.progress?.challenge_generation || 0)}%</span>
                </div>
                <div className="w-full bg-background border border-border rounded-full h-2 overflow-hidden">
                  <div
                    className="h-full bg-secondary transition-all duration-300"
                    style={{ width: `${status?.progress?.challenge_generation || 0}%` }}
                  />
                </div>
              </div>
            </div>

            {/* Topics Being Processed */}
            {status?.topics && status.topics.length > 0 && (
              <div className="mb-6">
                <h3 className="text-primary font-bold mb-3">Topics Detected:</h3>
                <div className="space-y-2">
                  {status.topics.map((topic) => (
                    <div
                      key={topic.id}
                      className="flex items-center gap-3 bg-surface border border-border rounded-lg p-3"
                    >
                      <div className="w-2 h-2 rounded-full bg-primary animate-pulse" />
                      <span className="text-gray-300 flex-1">{topic.title}</span>
                      <span className="text-gray-500 text-sm">{topic.challenges} challenges</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        {/* Real-time Logs */}
        <div className="bg-black border border-border rounded-lg p-4 font-mono text-sm">
          <div className="flex items-center gap-2 mb-3 pb-3 border-b border-border">
            <div className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            <span className="text-gray-400">Live Logs</span>
          </div>
          <div className="h-48 overflow-y-auto space-y-1">
            {logs.length === 0 ? (
              <div className="text-gray-500">Waiting for logs...</div>
            ) : (
              logs.map((log, idx) => (
                <div key={idx} className="flex gap-2">
                  <span className="text-gray-600">[{log.timestamp.split('T')[1]?.split('.')[0]}]</span>
                  <span className={`
                    ${log.level === 'error' ? 'text-red-400' : ''}
                    ${log.level === 'warn' ? 'text-amber-400' : ''}
                    ${log.level === 'info' ? 'text-gray-300' : ''}
                  `}>
                    {log.level.toUpperCase()}
                  </span>
                  <span className="text-gray-300">{log.message}</span>
                </div>
              ))
            )}
            <div ref={logsEndRef} />
          </div>
        </div>
      </div>
    )
  }

  // Results View
  if (view === 'results') {
    return (
      <div className="max-w-3xl mx-auto">
        <div className="text-center mb-8">
          <div className="text-5xl mb-4">✅</div>
          <h2 className="text-3xl font-bold text-primary mb-2">Course Generated!</h2>
          <p className="text-gray-400">Your interactive course is ready</p>
        </div>

        {status?.course ? (
          <div className="bg-surface border border-border rounded-lg p-6 mb-6">
            <h3 className="text-2xl font-bold text-gray-100 mb-2">{status.course.title}</h3>
            <p className="text-gray-400">{status.course.description}</p>
          </div>
        ) : (
          <div className="bg-surface border border-border rounded-lg p-6 mb-6">
            <h3 className="text-2xl font-bold text-gray-100 mb-2">Processing Complete</h3>
            <p className="text-gray-400">Your course has been generated but details are not yet available.</p>
          </div>
        )}

        {status?.topics && status.topics.length > 0 && (
          <div className="mb-8">
            <h3 className="text-primary font-bold mb-4">Course Structure:</h3>
            <div className="space-y-2">
              {status.topics.map((topic, idx) => (
                <div
                  key={topic.id}
                  className="flex items-center gap-4 bg-surface border border-border rounded-lg p-4"
                >
                  <div className="w-8 h-8 rounded-full bg-primary/20 border border-primary flex items-center justify-center text-primary font-bold text-sm">
                    {idx + 1}
                  </div>
                  <div className="flex-1">
                    <h4 className="text-gray-200 font-bold">{topic.title}</h4>
                  </div>
                  <div className="text-right">
                    <div className="text-amber-400 font-bold">{topic.challenges}</div>
                    <div className="text-gray-500 text-sm">challenges</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="flex gap-4">
          <button
            onClick={handleGoToCourse}
            className="flex-1 bg-primary text-black font-bold py-4 px-6 rounded-lg hover:bg-primary/90 transition-colors"
          >
            🚀 Go to Course
          </button>
          <button
            onClick={handleRetry}
            className="px-6 py-4 border border-border text-gray-400 hover:text-gray-200 hover:border-primary transition-colors rounded-lg"
          >
            Generate Another
          </button>
        </div>
      </div>
    )
  }

  // Error View
  if (view === 'error') {
    return (
      <div className="max-w-2xl mx-auto text-center">
        <div className="text-6xl mb-4">❌</div>
        <h2 className="text-3xl font-bold text-red-400 mb-2">Processing Failed</h2>
        <p className="text-gray-400 mb-6">{error}</p>

        <div className="bg-surface border border-red-900/50 rounded-lg p-4 mb-6">
          <h4 className="text-red-400 font-bold mb-2">Possible causes:</h4>
          <ul className="text-gray-400 text-sm space-y-1 text-left">
            <li>• File format not supported</li>
            <li>• Document too large or corrupted</li>
            <li>• Network connection interrupted</li>
            <li>• Backend service unavailable</li>
          </ul>
        </div>

        <button
          onClick={handleRetry}
          className="bg-primary text-black font-bold py-3 px-8 rounded-lg hover:bg-primary/90 transition-colors"
        >
          🔄 Try Again
        </button>
      </div>
    )
  }

  // Fallback for any unexpected state
  console.error('Grinder: Unexpected view state:', { view, status, error })
  return (
    <div className="max-w-2xl mx-auto text-center py-12">
      <div className="text-6xl mb-4">⚠️</div>
      <h2 className="text-3xl font-bold text-amber-400 mb-2">Unexpected Error</h2>
      <p className="text-gray-400 mb-6">The application encountered an unexpected state. Please try again.</p>
      <button
        onClick={handleRetry}
        className="bg-primary text-black font-bold py-3 px-8 rounded-lg hover:bg-primary/90 transition-colors"
      >
        🔄 Try Again
      </button>
    </div>
  )
}
