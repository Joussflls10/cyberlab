import { useEffect, useState, useCallback, useRef, useMemo } from 'react'
import { useParams, useNavigate, useLocation } from 'react-router-dom'
import {
  CheckCircle2,
  CheckSquare,
  Clock3,
  ListChecks,
  Square,
  TerminalSquare,
} from 'lucide-react'
import Terminal from '../components/Terminal'
import { getChallenge, startChallenge, submitChallenge, skipChallenge } from '../api/client'

type Phase = 'loading' | 'starting' | 'active' | 'submitting' | 'submitted' | 'error'
type ChallengeType = 'command' | 'output' | 'file'
type MobileView = 'steps' | 'terminal'

interface ChallengeData {
  id: string
  title: string
  type: ChallengeType
  difficulty: 'easy' | 'medium' | 'hard'
  question: string
  hint?: string
  sandbox_image?: string
  validation_script?: string
  expected_output?: string
  solution?: string
}

interface ChallengeRouteState {
  courseId?: string
  challengeIndex?: number
  challengeTotal?: number
  challengeIds?: string[]
}

interface SubmitResult {
  passed: boolean
  output: string
  expected?: string
  actual?: string
}

const CHECKLIST_STORAGE_PREFIX = 'cyberlab-checklist:'

function stripStepPrefix(line: string): string {
  return line
    .replace(/^\s*(\d+[.)]|[-*•])\s+/, '')
    .replace(/^\s*\[[ xX]\]\s+/, '')
    .trim()
}

function deriveChecklistSteps(question: string): string[] {
  const withoutCodeBlocks = question.replace(/```[\s\S]*?```/g, ' ').replace(/\r/g, '').trim()
  if (!withoutCodeBlocks) return []

  const lines = withoutCodeBlocks
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)

  const explicitSteps = lines
    .filter(line => /^(\d+[.)]|[-*•])\s+/.test(line))
    .map(stripStepPrefix)
    .filter(Boolean)

  if (explicitSteps.length < 2) return []
  return explicitSteps.slice(0, 12)
}

function deriveChallengeTitle(data: Pick<ChallengeData, 'title' | 'question'> | null | undefined): string {
  const explicitTitle = data?.title?.trim()
  if (explicitTitle) return explicitTitle

  const firstMeaningfulLine = (data?.question || '')
    .replace(/```[\s\S]*?```/g, ' ')
    .split('\n')
    .map(line => stripStepPrefix(line))
    .find(Boolean)

  if (!firstMeaningfulLine) return 'Challenge'
  return firstMeaningfulLine.length > 90
    ? `${firstMeaningfulLine.slice(0, 89).trimEnd()}…`
    : firstMeaningfulLine
}

export default function Challenge() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const location = useLocation()

  const [challenge, setChallenge] = useState<ChallengeData | null>(null)
  const [containerId, setContainerId] = useState<string | null>(null)
  const [ttydPort, setTtydPort] = useState<number | null>(null)
  const [phase, setPhase] = useState<Phase>('loading')
  const [result, setResult] = useState<SubmitResult | null>(null)
  const [showHint, setShowHint] = useState(false)
  const [showValidationScript, setShowValidationScript] = useState(false)
  const [showGiveUpDialog, setShowGiveUpDialog] = useState(false)
  const [showSuccessModal, setShowSuccessModal] = useState(false)
  const [showFailureModal, setShowFailureModal] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [mobileView, setMobileView] = useState<MobileView>('steps')
  const [checklist, setChecklist] = useState<boolean[]>([])

  const [timeSpent, setTimeSpent] = useState(0)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const [attempts, setAttempts] = useState(0)
  const [showSolution, setShowSolution] = useState(false)

  const routeState = (location.state ?? {}) as ChallengeRouteState

  const checklistSteps = useMemo(
    () => deriveChecklistSteps(challenge?.question ?? ''),
    [challenge?.question]
  )

  const completedSteps = checklist.filter(Boolean).length
  const checklistPercent = checklistSteps.length > 0
    ? Math.round((completedSteps / checklistSteps.length) * 100)
    : 0

  const showChecklist = useMemo(() => {
    if (!challenge || checklistSteps.length < 2) return false
    const questionLen = challenge.question.replace(/\s+/g, ' ').trim().length
    const checklistLen = checklistSteps.join(' ').replace(/\s+/g, ' ').trim().length
    return checklistLen < questionLen * 0.8
  }, [challenge, checklistSteps])

  const challengeTitle = useMemo(() => {
    if (!challenge) return 'Loading challenge…'
    return deriveChallengeTitle(challenge)
  }, [challenge])

  const challengeCounter = useMemo(() => {
    if (
      typeof routeState.challengeIndex !== 'number' ||
      typeof routeState.challengeTotal !== 'number' ||
      routeState.challengeTotal <= 0
    ) {
      return null
    }

    return `Challenge ${routeState.challengeIndex + 1} / ${routeState.challengeTotal}`
  }, [routeState.challengeIndex, routeState.challengeTotal])

  const terminalTitle = useMemo(() => {
    const image = challenge?.sandbox_image?.replace(/^cyberlab-/, '')
    if (!image) return 'CyberLab Sandbox'
    return `CyberLab Sandbox — ${image}`
  }, [challenge?.sandbox_image])

  const isActive = phase === 'active' || phase === 'submitting'

  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60)
    const secs = seconds % 60
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`
  }

  useEffect(() => {
    if (phase === 'active') {
      timerRef.current = setInterval(() => {
        setTimeSpent(t => t + 1)
      }, 1000)
    } else if (timerRef.current) {
      clearInterval(timerRef.current)
    }

    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [phase])

  useEffect(() => {
    setTimeSpent(0)
    setAttempts(0)
    setShowSolution(false)
    setMobileView('steps')
  }, [id])

  useEffect(() => {
    if (!id) return
    setPhase('loading')
    setError(null)

    getChallenge(id)
      .then(data => {
        const normalized = {
          ...data,
          title: deriveChallengeTitle(data),
        } as ChallengeData
        setChallenge(normalized)
        setPhase('starting')
      })
      .catch(() => {
        setError('Failed to load challenge data.')
        setPhase('error')
      })
  }, [id])

  useEffect(() => {
    if (phase !== 'starting' || !id) return

    startChallenge(id)
      .then(({ container_id, port }) => {
        setContainerId(container_id)
        setTtydPort(port)
        setPhase('active')
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to start sandbox container.')
        setPhase('error')
      })
  }, [phase, id])

  useEffect(() => {
    if (!id || checklistSteps.length === 0) {
      setChecklist([])
      return
    }

    try {
      const stored = localStorage.getItem(`${CHECKLIST_STORAGE_PREFIX}${id}`)
      if (!stored) {
        setChecklist(Array(checklistSteps.length).fill(false))
        return
      }

      const parsed = JSON.parse(stored)
      if (!Array.isArray(parsed)) {
        setChecklist(Array(checklistSteps.length).fill(false))
        return
      }

      const normalized = Array.from({ length: checklistSteps.length }, (_, idx) => parsed[idx] === true)
      setChecklist(normalized)
    } catch {
      setChecklist(Array(checklistSteps.length).fill(false))
    }
  }, [id, checklistSteps.length])

  useEffect(() => {
    if (!id || checklist.length === 0) return
    try {
      localStorage.setItem(`${CHECKLIST_STORAGE_PREFIX}${id}`, JSON.stringify(checklist))
    } catch {
      // ignore localStorage failures in private mode
    }
  }, [id, checklist])

  const toggleStep = (index: number) => {
    setChecklist(prev => prev.map((checked, idx) => (idx === index ? !checked : checked)))
  }

  const markAllSteps = (value: boolean) => {
    setChecklist(Array(checklistSteps.length).fill(value))
  }

  const handleSubmit = async () => {
    if (!id || !containerId) return

    setPhase('submitting')
    try {
      const res = await submitChallenge(id, containerId)
      setResult(res)

      if (res.passed) {
        setShowSuccessModal(true)
      } else {
        const nextAttempts = attempts + 1
        setAttempts(nextAttempts)
        if (nextAttempts >= 3) setShowSolution(true)
        setShowFailureModal(true)
      }
      setPhase('submitted')
    } catch {
      setError('Submission failed.')
      setPhase('active')
    }
  }

  const handleSkip = () => setShowGiveUpDialog(true)

  const confirmSkip = async () => {
    setShowGiveUpDialog(false)
    if (!id) return
    await skipChallenge(id)
    navigate(-1)
  }

  const handleRetry = () => {
    setPhase('active')
    setResult(null)
    setShowFailureModal(false)
  }

  const handleViewSolution = () => {
    setShowSolution(true)
    setShowFailureModal(false)
  }

  const handleNextChallenge = () => {
    setShowSuccessModal(false)

    const { challengeIds, challengeIndex, courseId } = routeState
    if (Array.isArray(challengeIds) && typeof challengeIndex === 'number') {
      const nextIndex = challengeIndex + 1
      if (nextIndex < challengeIds.length) {
        navigate(`/challenge/${challengeIds[nextIndex]}`, {
          state: {
            ...routeState,
            challengeIndex: nextIndex,
            challengeTotal: challengeIds.length,
          },
        })
        return
      }
    }

    if (courseId) {
      navigate(`/course/${courseId}`)
      return
    }

    navigate(-1)
  }

  const handleTerminalFocus = useCallback(() => {
    // hook for future terminal focus analytics
  }, [])

  const renderMarkdown = (text: string) => {
    if (!text) return null

    const parts = text.split(/(```[\s\S]*?```)/g)

    return parts.map((part, index) => {
      if (part.startsWith('```')) {
        const match = part.match(/```(\w*)\n([\s\S]*?)```/)
        if (match) {
          const [, lang, code] = match
          return (
            <pre key={index} className="my-2 p-3 bg-[#111] rounded border border-[#222] overflow-x-auto">
              <code className={`text-sm font-mono ${lang ? `language-${lang}` : ''}`}>
                {code.trim()}
              </code>
            </pre>
          )
        }
      }

      const lines = part.split('\n')
      return (
        <div key={index} className="space-y-1">
          {lines.map((line, lineIdx) => {
            const segments = line.split(/(`[^`]+`)/g)
            return (
              <p key={lineIdx} className="text-sm leading-relaxed break-words">
                {segments.map((segment, segIdx) => {
                  if (segment.startsWith('`') && segment.endsWith('`')) {
                    return (
                      <code
                        key={segIdx}
                        className="px-1.5 py-0.5 bg-[#222] rounded text-[#00ff88] text-xs font-mono"
                      >
                        {segment.slice(1, -1)}
                      </code>
                    )
                  }
                  return <span key={segIdx}>{segment}</span>
                })}
              </p>
            )
          })}
        </div>
      )
    })
  }

  const highlightSyntax = (code: string) => {
    const keywords = ['if', 'then', 'else', 'fi', 'for', 'do', 'done', 'while', 'case', 'esac', 'function', 'return', 'exit']
    const commands = ['echo', 'grep', 'sed', 'awk', 'cat', 'ls', 'cd', 'mkdir', 'rm', 'cp', 'mv', 'chmod', 'chown']

    return code.split('\n').map((line, idx) => {
      if (line.trim().startsWith('#')) {
        return <div key={idx} className="text-[#666]">{line}</div>
      }

      const words = line.split(/(\s+)/)
      return (
        <div key={idx}>
          {words.map((word, wIdx) => {
            if (keywords.includes(word.trim())) return <span key={wIdx} className="text-[#ffaa00]">{word}</span>
            if (commands.includes(word.trim())) return <span key={wIdx} className="text-[#00ff88]">{word}</span>
            if (word.startsWith('"') || word.startsWith("'")) return <span key={wIdx} className="text-[#ffaa00]">{word}</span>
            if (word.startsWith('$')) return <span key={wIdx} className="text-[#ff4444]">{word}</span>
            return <span key={wIdx}>{word}</span>
          })}
        </div>
      )
    })
  }

  if (phase === 'error') {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#0a0a0a] text-[#ff4444] font-mono px-4">
        <div className="text-center max-w-md">
          <div className="text-4xl mb-4">⚠️</div>
          <p className="text-sm mb-4">{error || 'Something went wrong.'}</p>
          <button
            onClick={() => navigate(-1)}
            className="px-4 py-2 bg-[#333] hover:bg-[#444] text-gray-300 rounded transition-colors"
          >
            Go Back
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen lg:h-screen bg-[#0a0a0a] text-gray-100 font-mono flex flex-col lg:flex-row overflow-hidden">
      <div className="lg:hidden sticky top-0 z-30 border-b border-[#222] bg-[#0f0f0f]/95 backdrop-blur px-3 py-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="text-sm font-semibold text-gray-100 truncate">{challengeTitle}</h1>
            <div className="mt-1 flex items-center gap-2 text-xs text-gray-500">
              {challengeCounter && (
                <span className="px-1.5 py-0.5 rounded border border-[#333] text-gray-300 bg-[#111]">
                  {challengeCounter}
                </span>
              )}
              <Clock3 className="w-3.5 h-3.5" />
              <span className={timeSpent > 300 ? 'text-[#ffaa00]' : ''}>{formatTime(timeSpent)}</span>
              {challenge && (
                <span className={`ml-1 px-1.5 py-0.5 rounded border ${
                  challenge.difficulty === 'easy' ? 'border-[#00ff88] text-[#00ff88]' :
                  challenge.difficulty === 'medium' ? 'border-[#ffaa00] text-[#ffaa00]' :
                  'border-[#ff4444] text-[#ff4444]'
                }`}>
                  {challenge.difficulty}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-2">
          <button
            onClick={() => setMobileView('steps')}
            className={`inline-flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-xs ${
              mobileView === 'steps'
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-[#333] text-gray-400'
            }`}
          >
            <ListChecks className="w-3.5 h-3.5" />
            Steps
          </button>
          <button
            onClick={() => setMobileView('terminal')}
            className={`inline-flex items-center justify-center gap-2 rounded-md border px-3 py-2 text-xs ${
              mobileView === 'terminal'
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-[#333] text-gray-400'
            }`}
          >
            <TerminalSquare className="w-3.5 h-3.5" />
            Terminal
          </button>
        </div>
      </div>

      <aside className={`${mobileView === 'steps' ? 'flex' : 'hidden'} lg:flex w-full lg:w-[420px] flex-col border-r border-[#222] bg-[#0f0f0f] lg:bg-transparent`}>
        <div className="hidden lg:block p-4 border-b border-[#222] bg-[#0f0f0f]">
          <div className="flex flex-wrap items-center gap-2 mb-3">
            {challenge && (
              <span className={`text-xs px-2 py-1 rounded border ${
                challenge.difficulty === 'easy' ? 'border-[#00ff88] text-[#00ff88]' :
                challenge.difficulty === 'medium' ? 'border-[#ffaa00] text-[#ffaa00]' :
                'border-[#ff4444] text-[#ff4444]'
              }`}>
                {challenge.difficulty.toUpperCase()}
              </span>
            )}

            <div className="flex items-center gap-1.5 text-xs text-[#c7c7c7] bg-[#111] px-2 py-1 rounded border border-[#2a2a2a]">
              <Clock3 className="w-3.5 h-3.5 text-[#666]" />
              <span className={timeSpent > 300 ? 'text-[#ffaa00]' : ''}>{formatTime(timeSpent)}</span>
            </div>

            {challengeCounter && (
              <span className="text-xs text-gray-300 px-2 py-1 bg-[#111] rounded border border-[#2a2a2a]">
                {challengeCounter}
              </span>
            )}

            {challenge && (
              <span className="text-xs text-[#666] px-2 py-1 bg-[#111] rounded border border-[#2a2a2a]">
                {challenge.type}
              </span>
            )}
          </div>

          <h1 className="text-lg font-bold text-gray-100">{challengeTitle}</h1>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4 pb-24 lg:pb-4">
          {challenge ? (
            <>
              <div className="bg-[#111] rounded border border-[#222] p-4">
                <h2 className="text-xs text-[#666] uppercase tracking-wide mb-2">Challenge</h2>
                <div className="text-gray-200">{renderMarkdown(challenge.question)}</div>
              </div>

              {showChecklist && (
                <div className="bg-[#111] rounded border border-primary/20 p-4">
                  <div className="flex items-center justify-between mb-3 gap-3">
                    <div>
                      <h2 className="text-xs text-primary uppercase tracking-wide">Step checklist</h2>
                      <p className="text-xs text-gray-500 mt-1">{completedSteps}/{checklistSteps.length} completed</p>
                    </div>
                    <span className="text-sm font-semibold text-primary">{checklistPercent}%</span>
                  </div>

                  <div className="w-full h-2 bg-[#0a0a0a] border border-[#222] rounded-full overflow-hidden mb-3">
                    <div className="h-full bg-primary transition-all duration-300" style={{ width: `${checklistPercent}%` }} />
                  </div>

                  <div className="space-y-2">
                    {checklistSteps.map((step, idx) => {
                      const checked = checklist[idx] === true
                      return (
                        <button
                          key={`${step}-${idx}`}
                          onClick={() => toggleStep(idx)}
                          className={`w-full text-left rounded-md border px-3 py-2 text-sm transition-colors ${
                            checked
                              ? 'border-primary/40 bg-primary/10 text-gray-100'
                              : 'border-[#2a2a2a] bg-[#0d0d0d] text-gray-300'
                          }`}
                        >
                          <span className="inline-flex items-start gap-2">
                            {checked ? <CheckSquare className="w-4 h-4 mt-0.5 text-primary" /> : <Square className="w-4 h-4 mt-0.5 text-gray-500" />}
                            <span className={checked ? 'line-through text-gray-400' : ''}>{step}</span>
                          </span>
                        </button>
                      )
                    })}
                  </div>

                  <div className="mt-3 flex items-center gap-2">
                    <button
                      onClick={() => markAllSteps(true)}
                      className="text-xs border border-primary/30 text-primary px-2 py-1 rounded hover:bg-primary/10"
                    >
                      Check all
                    </button>
                    <button
                      onClick={() => markAllSteps(false)}
                      className="text-xs border border-[#333] text-gray-400 px-2 py-1 rounded hover:border-[#555]"
                    >
                      Reset
                    </button>
                  </div>
                </div>
              )}

              {challenge.hint && (
                <div className="bg-[#111] rounded border border-[#ffaa00]/30 p-4">
                  <button
                    onClick={() => setShowHint(h => !h)}
                    className="text-xs text-[#ffaa00] hover:text-[#ffcc00] flex items-center gap-1 mb-2"
                  >
                    <span>{showHint ? '▼' : '▶'}</span>
                    <span>Hint</span>
                  </button>
                  {showHint && (
                    <div className="text-xs text-[#ffaa00]/80 border-l-2 border-[#ffaa00]/50 pl-3 mt-2">
                      {renderMarkdown(challenge.hint)}
                    </div>
                  )}
                </div>
              )}

              {challenge.validation_script && (
                <div className="bg-[#111] rounded border border-[#222] p-4">
                  <button
                    onClick={() => setShowValidationScript(v => !v)}
                    className="text-xs text-[#666] hover:text-gray-300 flex items-center gap-1 mb-2"
                  >
                    <span>{showValidationScript ? '▼' : '▶'}</span>
                    <span>Validation Script</span>
                  </button>
                  {showValidationScript && (
                    <pre className="text-xs text-gray-400 bg-[#0a0a0a] rounded p-3 overflow-x-auto border border-[#222]">
                      <code>{highlightSyntax(challenge.validation_script)}</code>
                    </pre>
                  )}
                </div>
              )}

              {challenge.type === 'output' && challenge.expected_output && (
                <div className="bg-[#111] rounded border border-[#222] p-4">
                  <h2 className="text-xs text-[#666] uppercase tracking-wide mb-2">Expected Output</h2>
                  <pre className="text-xs text-[#00ff88] bg-[#0a0a0a] rounded p-3 overflow-x-auto border border-[#222]">
                    <code>{challenge.expected_output}</code>
                  </pre>
                </div>
              )}

              {showSolution && challenge.solution && (
                <div className="bg-[#111] rounded border border-[#00ff88]/30 p-4">
                  <h2 className="text-xs text-[#00ff88] uppercase tracking-wide mb-2">Solution</h2>
                  <pre className="text-xs text-gray-300 bg-[#0a0a0a] rounded p-3 overflow-x-auto border border-[#222]">
                    <code>{highlightSyntax(challenge.solution)}</code>
                  </pre>
                </div>
              )}
            </>
          ) : (
            <div className="text-[#666] text-sm animate-pulse">Loading challenge...</div>
          )}
        </div>

        <div className="hidden lg:block p-4 border-t border-[#222] bg-[#0f0f0f] space-y-2">
          {isActive && (
            <>
              <button
                onClick={handleSubmit}
                disabled={phase === 'submitting'}
                className="w-full py-2.5 bg-[#2f8f5f] hover:bg-[#37a26a] text-[#f4fff8] font-bold rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {phase === 'submitting' ? (
                  <>
                    <div className="w-4 h-4 border-2 border-[#f4fff8] border-t-transparent rounded-full animate-spin" />
                    <span>Validating...</span>
                  </>
                ) : (
                  <>
                    <span>✓ Submit Solution</span>
                  </>
                )}
              </button>

              <div className="flex gap-2">
                <button
                  onClick={handleSkip}
                  className="flex-1 py-2 border border-[#333] hover:border-[#ff4444] hover:text-[#ff4444] text-gray-400 rounded transition-colors text-sm"
                >
                  Give Up
                </button>
                {showSolution && (
                  <button
                    onClick={() => {}}
                    className="flex-1 py-2 border border-[#00ff88]/30 text-[#00ff88] rounded transition-colors text-sm"
                  >
                    View Solution
                  </button>
                )}
              </div>

              {attempts > 0 && (
                <p className="text-xs text-[#666] text-center">
                  Attempts: <span className={attempts >= 3 ? 'text-[#ff4444]' : 'text-[#ffaa00]'}>{attempts}</span>
                </p>
              )}
            </>
          )}

          {(phase === 'loading' || phase === 'starting') && (
            <button
              disabled
              className="w-full py-2.5 bg-[#222] text-[#666] rounded cursor-not-allowed"
            >
              Initializing...
            </button>
          )}
        </div>
      </aside>

      <section
        className={`${mobileView === 'terminal' ? 'flex' : 'hidden'} lg:flex flex-1 min-h-[55vh] lg:min-h-0`}
        style={mobileView === 'terminal' ? { height: 'calc(100vh - 170px)' } : undefined}
      >
        <div className="flex-1 relative">
          <Terminal port={ttydPort} onFocus={handleTerminalFocus} title={terminalTitle} />
        </div>
      </section>

      <div className="lg:hidden sticky bottom-0 z-20 border-t border-[#222] bg-[#0f0f0f]/95 backdrop-blur px-3 py-3 space-y-2">
        {isActive && (
          <>
            <button
              onClick={handleSubmit}
              disabled={phase === 'submitting'}
              className="w-full py-2.5 bg-[#2f8f5f] hover:bg-[#37a26a] text-[#f4fff8] font-semibold rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
            >
              {phase === 'submitting' ? (
                <>
                  <div className="w-4 h-4 border-2 border-[#f4fff8] border-t-transparent rounded-full animate-spin" />
                  <span>Validating...</span>
                </>
              ) : (
                <>
                  <CheckCircle2 className="w-4 h-4" />
                  <span>Submit</span>
                </>
              )}
            </button>

            <button
              onClick={handleSkip}
              className="w-full py-2 border border-[#333] text-gray-400 rounded hover:border-[#ff4444] hover:text-[#ff4444] transition-colors text-sm"
            >
              Give Up
            </button>
          </>
        )}
      </div>

      {showSuccessModal && result?.passed && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-40 p-4">
          <div className="border border-[#00ff88] shadow-[0_0_40px_rgba(0,255,136,0.3)] rounded-lg p-6 sm:p-8 max-w-md w-full bg-[#111]">
            <div className="text-center mb-6">
              <div className="text-5xl mb-4">🎉</div>
              <h2 className="text-2xl font-bold text-[#00ff88] mb-2">Challenge Completed!</h2>
              <p className="text-gray-400 text-sm">Great job! You've successfully solved this challenge.</p>
            </div>

            {result.output && (
              <div className="mb-6">
                <p className="text-xs text-[#666] mb-2">Output:</p>
                <pre className="text-xs text-gray-400 bg-[#0a0a0a] rounded p-3 overflow-auto max-h-32 border border-[#222]">
                  {result.output}
                </pre>
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={() => {
                  setShowSuccessModal(false)
                  setPhase('active')
                }}
                className="flex-1 py-2.5 border border-[#333] text-gray-400 rounded hover:border-[#555] transition-colors"
              >
                Stay Here
              </button>
              <button
                onClick={handleNextChallenge}
                className="flex-1 py-2.5 bg-[#00ff88] text-black font-bold rounded hover:bg-[#00ff88]/90 transition-colors"
              >
                Continue →
              </button>
            </div>
          </div>
        </div>
      )}

      {showFailureModal && result && !result.passed && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-40 p-4">
          <div className="border border-[#ff4444] shadow-[0_0_40px_rgba(255,68,68,0.2)] rounded-lg p-6 sm:p-8 max-w-md w-full bg-[#111]">
            <div className="text-center mb-6">
              <div className="text-5xl mb-4">💀</div>
              <h2 className="text-2xl font-bold text-[#ff4444] mb-2">Not Quite Right</h2>
              <p className="text-gray-400 text-sm">Your solution didn't pass validation.</p>
            </div>

            <div className="mb-6 space-y-4">
              {result.expected && (
                <div>
                  <p className="text-xs text-[#666] mb-1">Expected:</p>
                  <pre className="text-xs text-[#00ff88] bg-[#0a0a0a] rounded p-3 overflow-auto max-h-24 border border-[#222]">
                    {result.expected}
                  </pre>
                </div>
              )}

              {result.actual && (
                <div>
                  <p className="text-xs text-[#666] mb-1">Your output:</p>
                  <pre className="text-xs text-[#ff4444] bg-[#0a0a0a] rounded p-3 overflow-auto max-h-24 border border-[#222]">
                    {result.actual}
                  </pre>
                </div>
              )}

              {result.output && !result.expected && (
                <div>
                  <p className="text-xs text-[#666] mb-1">Validator output:</p>
                  <pre className="text-xs text-gray-400 bg-[#0a0a0a] rounded p-3 overflow-auto max-h-24 border border-[#222]">
                    {result.output}
                  </pre>
                </div>
              )}
            </div>

            {attempts >= 3 && !showSolution && (
              <div className="mb-4 p-3 bg-[#ffaa00]/10 border border-[#ffaa00]/30 rounded">
                <p className="text-xs text-[#ffaa00] text-center">💡 After 3 failed attempts, you can view the solution</p>
              </div>
            )}

            <div className="flex gap-3">
              <button
                onClick={handleRetry}
                className="flex-1 py-2.5 bg-[#ffaa00] text-black font-bold rounded hover:bg-[#ffaa00]/90 transition-colors"
              >
                Try Again
              </button>
              {!showSolution ? (
                <button
                  onClick={handleViewSolution}
                  disabled={attempts < 3}
                  className="flex-1 py-2.5 border border-[#333] text-gray-400 rounded hover:border-[#555] transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  View Solution
                </button>
              ) : (
                <button
                  onClick={() => setShowSolution(true)}
                  className="flex-1 py-2.5 border border-[#00ff88]/30 text-[#00ff88] rounded hover:bg-[#00ff88]/10 transition-colors"
                >
                  Show Solution
                </button>
              )}
            </div>
          </div>
        </div>
      )}

      {showGiveUpDialog && (
        <div className="fixed inset-0 bg-black/80 flex items-center justify-center z-40 p-4">
          <div className="border border-[#ffaa00] rounded-lg p-6 max-w-sm w-full bg-[#111]">
            <div className="text-center mb-4">
              <div className="text-4xl mb-3">🏳️</div>
              <h2 className="text-xl font-bold text-[#ffaa00] mb-2">Give Up?</h2>
              <p className="text-gray-400 text-sm">You'll lose progress on this challenge. Are you sure?</p>
            </div>

            <div className="flex gap-3">
              <button
                onClick={() => setShowGiveUpDialog(false)}
                className="flex-1 py-2.5 border border-[#333] text-gray-400 rounded hover:border-[#555] transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={confirmSkip}
                className="flex-1 py-2.5 bg-[#ff4444] text-white font-bold rounded hover:bg-[#ff4444]/90 transition-colors"
              >
                Yes, Skip
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="hidden lg:block absolute bottom-4 right-4 text-xs text-[#666] bg-[#111]/80 px-2 py-1 rounded pointer-events-none">
        Press F2 (or Ctrl+`) to focus terminal
      </div>
    </div>
  )
}
