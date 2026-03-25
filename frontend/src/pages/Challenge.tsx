import { useEffect, useState, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Terminal from '../components/Terminal';
import { getChallenge, startChallenge, submitChallenge, skipChallenge } from '../api/client';

type Phase = 'loading' | 'starting' | 'active' | 'submitting' | 'submitted' | 'error';
type ChallengeType = 'command' | 'output' | 'file';

interface ChallengeData {
  id: string;
  title: string;
  type: ChallengeType;
  difficulty: 'easy' | 'medium' | 'hard';
  question: string;
  hint?: string;
  validation_script?: string;
  expected_output?: string;
  solution?: string;
}

interface SubmitResult {
  passed: boolean;
  output: string;
  expected?: string;
  actual?: string;
}

export default function Challenge() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [challenge, setChallenge] = useState<ChallengeData | null>(null);
  const [containerId, setContainerId] = useState<string | null>(null);
  const [ttydPort, setTtydPort] = useState<number | null>(null);
  const [phase, setPhase] = useState<Phase>('loading');
  const [result, setResult] = useState<SubmitResult | null>(null);
  const [showHint, setShowHint] = useState(false);
  const [showValidationScript, setShowValidationScript] = useState(false);
  const [showGiveUpDialog, setShowGiveUpDialog] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [showFailureModal, setShowFailureModal] = useState(false);
  const [error, setError] = useState<string | null>(null);
  
  // Timer state
  const [timeSpent, setTimeSpent] = useState(0);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  
  // Attempt tracking
  const [attempts, setAttempts] = useState(0);
  const [showSolution, setShowSolution] = useState(false);

  // Format time as MM:SS
  const formatTime = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  // Start timer when challenge becomes active
  useEffect(() => {
    if (phase === 'active') {
      timerRef.current = setInterval(() => {
        setTimeSpent(t => t + 1);
      }, 1000);
    } else {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
      }
    };
  }, [phase]);

  // Reset timer when challenge ID changes
  useEffect(() => {
    setTimeSpent(0);
    setAttempts(0);
    setShowSolution(false);
  }, [id]);

  // Step 1 — load challenge data
  useEffect(() => {
    if (!id) return;
    setPhase('loading');
    setError(null);
    
    getChallenge(id)
      .then(data => {
        setChallenge(data);
        setPhase('starting');
      })
      .catch(() => {
        setError('Failed to load challenge data.');
        setPhase('error');
      });
  }, [id]);

  // Step 2 — start sandbox once challenge is loaded
  useEffect(() => {
    if (phase !== 'starting' || !id) return;
    
    startChallenge(id)
      .then(({ container_id, ttyd_port }) => {
        setContainerId(container_id);
        setTtydPort(ttyd_port);
        setPhase('active');
      })
      .catch(() => {
        setError('Failed to start sandbox container.');
        setPhase('error');
      });
  }, [phase, id]);

  const handleSubmit = async () => {
    if (!id || !containerId) return;
    
    setPhase('submitting');
    try {
      const res = await submitChallenge(id, containerId);
      setResult(res);
      
      if (res.passed) {
        setShowSuccessModal(true);
      } else {
        const newAttempts = attempts + 1;
        setAttempts(newAttempts);
        
        // Show solution after 3 failed attempts
        if (newAttempts >= 3) {
          setShowSolution(true);
        }
        
        setShowFailureModal(true);
      }
      setPhase('submitted');
    } catch {
      setError('Submission failed.');
      setPhase('active');
    }
  };

  const handleSkip = () => {
    setShowGiveUpDialog(true);
  };

  const confirmSkip = async () => {
    setShowGiveUpDialog(false);
    if (!id) return;
    await skipChallenge(id);
    navigate(-1);
  };

  const handleRetry = () => {
    setPhase('active');
    setResult(null);
    setShowFailureModal(false);
  };

  const handleViewSolution = () => {
    setShowSolution(true);
    setShowFailureModal(false);
  };

  const handleNextChallenge = () => {
    setShowSuccessModal(false);
    navigate(-1); // Navigate back to course/topic
  };

  const handleTerminalFocus = useCallback(() => {
    // Terminal is focused
  }, []);

  // Simple markdown renderer with syntax highlighting
  const renderMarkdown = (text: string) => {
    if (!text) return null;
    
    // Split by code blocks first
    const parts = text.split(/(```[\s\S]*?```)/g);
    
    return parts.map((part, index) => {
      if (part.startsWith('```')) {
        // Extract language and code
        const match = part.match(/```(\w*)\n([\s\S]*?)```/);
        if (match) {
          const [, lang, code] = match;
          return (
            <pre key={index} className="my-2 p-3 bg-[#111] rounded border border-[#222] overflow-x-auto">
              <code className={`text-sm font-mono ${lang ? `language-${lang}` : ''}`}>
                {code.trim()}
              </code>
            </pre>
          );
        }
      }
      
      // Handle inline code and basic formatting
      const lines = part.split('\n');
      return (
        <div key={index} className="space-y-1">
          {lines.map((line, lineIdx) => {
            // Handle inline code
            const segments = line.split(/(`[^`]+`)/g);
            return (
              <p key={lineIdx} className="text-sm leading-relaxed">
                {segments.map((segment, segIdx) => {
                  if (segment.startsWith('`') && segment.endsWith('`')) {
                    return (
                      <code
                        key={segIdx}
                        className="px-1.5 py-0.5 bg-[#222] rounded text-[#00ff88] text-xs font-mono"
                      >
                        {segment.slice(1, -1)}
                      </code>
                    );
                  }
                  return <span key={segIdx}>{segment}</span>;
                })}
              </p>
            );
          })}
        </div>
      );
    });
  };

  // Syntax highlighting for validation script
  const highlightSyntax = (code: string) => {
    // Basic bash/shell highlighting
    const keywords = ['if', 'then', 'else', 'fi', 'for', 'do', 'done', 'while', 'case', 'esac', 'function', 'return', 'exit'];
    const commands = ['echo', 'grep', 'sed', 'awk', 'cat', 'ls', 'cd', 'mkdir', 'rm', 'cp', 'mv', 'chmod', 'chown'];
    
    return code.split('\n').map((line, idx) => {
      // Skip comments
      if (line.trim().startsWith('#')) {
        return <div key={idx} className="text-[#666]">{line}</div>;
      }
      
      const words = line.split(/(\s+)/);
      return (
        <div key={idx}>
          {words.map((word, wIdx) => {
            if (keywords.includes(word.trim())) {
              return <span key={wIdx} className="text-[#ffaa00]">{word}</span>;
            }
            if (commands.includes(word.trim())) {
              return <span key={wIdx} className="text-[#00ff88]">{word}</span>;
            }
            if (word.startsWith('"') || word.startsWith("'")) {
              return <span key={wIdx} className="text-[#ffaa00]">{word}</span>;
            }
            if (word.startsWith('$')) {
              return <span key={wIdx} className="text-[#ff4444]">{word}</span>;
            }
            return <span key={wIdx}>{word}</span>;
          })}
        </div>
      );
    });
  };

  if (phase === 'error') {
    return (
      <div className="flex items-center justify-center h-screen bg-[#0a0a0a] text-[#ff4444] font-mono">
        <div className="text-center">
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
    );
  }

  return (
    <div className="flex h-screen bg-[#0a0a0a] text-gray-100 font-mono overflow-hidden">
      {/* Left sidebar - Challenge details */}
      <div className="w-[420px] flex-shrink-0 border-r border-[#222] flex flex-col">
        {/* Header */}
        <div className="p-4 border-b border-[#222] bg-[#0f0f0f]">
          <div className="flex items-start justify-between mb-3">
            <div className="flex items-center gap-2">
              {challenge && (
                <>
                  <span className={`text-xs px-2 py-1 rounded border ${
                    challenge.difficulty === 'easy' ? 'border-[#00ff88] text-[#00ff88]' :
                    challenge.difficulty === 'medium' ? 'border-[#ffaa00] text-[#ffaa00]' :
                    'border-[#ff4444] text-[#ff4444]'
                  }`}>
                    {challenge.difficulty.toUpperCase()}
                  </span>
                  <span className="text-xs text-[#666] px-2 py-1 bg-[#111] rounded">
                    {challenge.type}
                  </span>
                </>
              )}
            </div>
            
            {/* Timer */}
            <div className="flex items-center gap-1.5 text-xs text-[#666] bg-[#111] px-2 py-1 rounded">
              <span>⏱️</span>
              <span className={timeSpent > 300 ? 'text-[#ffaa00]' : ''}>
                {formatTime(timeSpent)}
              </span>
            </div>
          </div>
          
          <h1 className="text-lg font-bold text-gray-100">
            {challenge?.title || 'Loading...'}
          </h1>
        </div>

        {/* Scrollable content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {challenge ? (
            <>
              {/* Question */}
              <div className="bg-[#111] rounded border border-[#222] p-4">
                <h2 className="text-xs text-[#666] uppercase tracking-wide mb-2">Challenge</h2>
                <div className="text-gray-200">
                  {renderMarkdown(challenge.question)}
                </div>
              </div>

              {/* Hint */}
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

              {/* Validation Script Preview */}
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

              {/* Expected Output Preview */}
              {challenge.type === 'output' && challenge.expected_output && (
                <div className="bg-[#111] rounded border border-[#222] p-4">
                  <h2 className="text-xs text-[#666] uppercase tracking-wide mb-2">Expected Output</h2>
                  <pre className="text-xs text-[#00ff88] bg-[#0a0a0a] rounded p-3 overflow-x-auto border border-[#222]">
                    <code>{challenge.expected_output}</code>
                  </pre>
                </div>
              )}

              {/* Solution (shown after 3 failures) */}
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

        {/* Action buttons */}
        <div className="p-4 border-t border-[#222] bg-[#0f0f0f] space-y-2">
          {(phase === 'active' || phase === 'submitting') && (
            <>
              <button
                onClick={handleSubmit}
                disabled={phase === ('submitting' as Phase)}
                className="w-full py-2.5 bg-[#00ff88] hover:bg-[#00ff88]/90 text-black font-bold rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {phase === ('submitting' as Phase) ? (
                  <>
                    <div className="w-4 h-4 border-2 border-black border-t-transparent rounded-full animate-spin" />
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
      </div>

      {/* Terminal panel */}
      <div className="flex-1 flex flex-col relative">
        <Terminal port={ttydPort} onFocus={handleTerminalFocus} />
      </div>

      {/* Success Modal */}
      {showSuccessModal && result?.passed && (
        <div className="absolute inset-0 bg-black/80 flex items-center justify-center z-20">
          <div className="border border-[#00ff88] shadow-[0_0_40px_rgba(0,255,136,0.3)] rounded-lg p-8 max-w-md w-full mx-4 bg-[#111]">
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
                onClick={() => { setShowSuccessModal(false); setPhase('active'); }}
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

      {/* Failure Modal */}
      {showFailureModal && result && !result.passed && (
        <div className="absolute inset-0 bg-black/80 flex items-center justify-center z-20">
          <div className="border border-[#ff4444] shadow-[0_0_40px_rgba(255,68,68,0.2)] rounded-lg p-8 max-w-md w-full mx-4 bg-[#111]">
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
                <p className="text-xs text-[#ffaa00] text-center">
                  💡 After 3 failed attempts, you can view the solution
                </p>
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

      {/* Give Up Confirmation Dialog */}
      {showGiveUpDialog && (
        <div className="absolute inset-0 bg-black/80 flex items-center justify-center z-20">
          <div className="border border-[#ffaa00] rounded-lg p-6 max-w-sm w-full mx-4 bg-[#111]">
            <div className="text-center mb-4">
              <div className="text-4xl mb-3">🏳️</div>
              <h2 className="text-xl font-bold text-[#ffaa00] mb-2">Give Up?</h2>
              <p className="text-gray-400 text-sm">
                You'll lose progress on this challenge. Are you sure?
              </p>
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
    </div>
  );
}
