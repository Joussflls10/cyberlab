import { useEffect, useState, useRef, useCallback } from 'react';

interface TerminalProps {
  port: number | null;
  onFocus?: () => void;
  title?: string;
}

type Status = 'waiting' | 'connecting' | 'connected' | 'disconnected' | 'error';

export default function Terminal({ port, onFocus, title = 'CyberLab Sandbox' }: TerminalProps) {
  const [status, setStatus] = useState<Status>('waiting');
  const [showReconnect, setShowReconnect] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const focusTerminal = useCallback(() => {
    if (!iframeRef.current || status !== 'connected') return;
    iframeRef.current.focus();
    try {
      iframeRef.current.contentWindow?.focus();
    } catch {
      // Cross-origin focus can fail silently depending on browser policy.
    }
    onFocus?.();
  }, [status, onFocus]);

  // Register keyboard shortcuts to focus terminal quickly.
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isFocusShortcut = e.key === 'F2' || (e.ctrlKey && e.key === '`');
      if (isFocusShortcut) {
        e.preventDefault();
        focusTerminal();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [focusTerminal]);

  // Poll for terminal readiness
  useEffect(() => {
    if (!port) {
      setStatus('waiting');
      return;
    }

    setStatus('connecting');
    setShowReconnect(false);

    let attempts = 0;
    const maxAttempts = 30; // 15 seconds
    const pollInterval = 500;

    const poll = setInterval(async () => {
      attempts++;
      try {
        await fetch(`http://localhost:${port}`, { mode: 'no-cors' });
        setStatus('connected');
        clearInterval(poll);
      } catch {
        if (attempts >= maxAttempts) {
          setStatus('error');
          setShowReconnect(true);
          clearInterval(poll);
        }
      }
    }, pollInterval);

    return () => clearInterval(poll);
  }, [port]);

  // Monitor iframe for disconnection
  useEffect(() => {
    if (status !== 'connected' || !iframeRef.current) return;

    let checkInterval: ReturnType<typeof setInterval>;

    const checkConnection = () => {
      if (!port) return;
      fetch(`http://localhost:${port}`, { mode: 'no-cors' })
        .catch(() => {
          setStatus('disconnected');
          setShowReconnect(true);
        });
    };

    checkInterval = setInterval(checkConnection, 5000);

    return () => clearInterval(checkInterval);
  }, [status, port]);

  const handleReconnect = useCallback(() => {
    if (!port) return;
    setStatus('connecting');
    setShowReconnect(false);

    let attempts = 0;
    const maxAttempts = 20;

    const poll = setInterval(async () => {
      attempts++;
      try {
        await fetch(`http://localhost:${port}`, { mode: 'no-cors' });
        setStatus('connected');
        clearInterval(poll);
      } catch {
        if (attempts >= maxAttempts) {
          setStatus('error');
          setShowReconnect(true);
          clearInterval(poll);
        }
      }
    }, 500);
  }, [port]);

  const handleIframeLoad = () => {
    if (status === 'connecting') {
      setStatus('connected');
    }

    window.setTimeout(() => {
      focusTerminal();
    }, 120);
  };

  useEffect(() => {
    if (status !== 'connected') return;

    const timer = window.setTimeout(() => {
      focusTerminal();
    }, 150);

    return () => window.clearTimeout(timer);
  }, [status, focusTerminal]);

  const getStatusColor = () => {
    switch (status) {
      case 'connecting': return '#ffaa00';
      case 'connected': return '#00ff88';
      case 'disconnected': return '#ffaa00';
      case 'error': return '#ff4444';
      default: return '#666';
    }
  };

  const getStatusText = () => {
    switch (status) {
      case 'waiting': return 'Waiting for container...';
      case 'connecting': return 'Connecting to terminal...';
      case 'connected': return 'Terminal ready';
      case 'disconnected': return 'Connection lost';
      case 'error': return 'Failed to connect';
    }
  };

  // Render status indicator
  const StatusIndicator = () => (
    <div className="flex items-center gap-2 px-2.5 py-1.5 bg-[#0f0f0f] rounded border border-[#2b2b2b]">
      <div
        className="w-2 h-2 rounded-full animate-pulse"
        style={{ backgroundColor: getStatusColor() }}
      />
      <span className="text-[11px] font-mono" style={{ color: getStatusColor() }}>
        {getStatusText()}
      </span>
      {showReconnect && (
        <button
          onClick={handleReconnect}
          className="ml-1 px-2 py-0.5 text-[11px] bg-[#262626] hover:bg-[#333] rounded transition-colors"
          style={{ color: '#ffaa00' }}
        >
          Reconnect
        </button>
      )}
    </div>
  );

  if (status === 'waiting') {
    return (
      <div
        ref={containerRef}
        className="relative flex items-center justify-center h-full bg-[#0a0a0a]"
        style={{ fontFamily: 'JetBrains Mono, monospace' }}
      >
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-[#333] border-t-[#00ff88] rounded-full animate-spin mx-auto mb-4" />
          <p className="text-[#00ff88] text-sm animate-pulse">Initializing sandbox...</p>
        </div>
      </div>
    );
  }

  if (status === 'connecting') {
    return (
      <div
        ref={containerRef}
        className="relative flex items-center justify-center h-full bg-[#0a0a0a]"
        style={{ fontFamily: 'JetBrains Mono, monospace' }}
      >
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-[#333] border-t-[#ffaa00] rounded-full animate-spin mx-auto mb-4" />
          <p className="text-[#ffaa00] text-sm animate-pulse">Establishing connection...</p>
          <p className="text-[#666] text-xs mt-2">Port: {port}</p>
        </div>
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div
        ref={containerRef}
        className="relative flex items-center justify-center h-full bg-[#0a0a0a]"
        style={{ fontFamily: 'JetBrains Mono, monospace' }}
      >
        <div className="text-center">
          <div className="text-4xl mb-4">💀</div>
          <p className="text-[#ff4444] text-sm mb-4">Terminal connection failed</p>
          {showReconnect && (
            <button
              onClick={handleReconnect}
              className="px-4 py-2 bg-[#ff4444]/20 hover:bg-[#ff4444]/30 text-[#ff4444] border border-[#ff4444] rounded transition-colors"
            >
              Try Again
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div
      ref={containerRef}
      className="relative h-full bg-[#050505] border border-[#1f1f1f] rounded-md overflow-hidden shadow-[0_0_30px_rgba(0,0,0,0.35)]"
      style={{ fontFamily: 'JetBrains Mono, monospace' }}
    >
      {/* Terminal header bar */}
      <div className="absolute top-0 left-0 right-0 h-10 bg-gradient-to-b from-[#121212] to-[#0d0d0d] border-b border-[#232323] flex items-center px-3 gap-3">
        <div className="flex items-center gap-2 shrink-0">
          <div className="w-3 h-3 rounded-full bg-[#ff4444]" />
          <div className="w-3 h-3 rounded-full bg-[#ffaa00]" />
          <div className="w-3 h-3 rounded-full bg-[#00ff88]" />
        </div>
        <span className="text-xs text-[#9a9a9a] truncate">{title}</span>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={focusTerminal}
            className="text-[11px] px-2 py-1 rounded border border-[#2d2d2d] bg-[#111] text-[#9a9a9a] hover:text-[#d0d0d0] hover:border-[#444] transition-colors"
          >
            Focus (F2)
          </button>
          <StatusIndicator />
        </div>
      </div>

      <iframe
        ref={iframeRef}
        src={`http://localhost:${port}`}
        className="absolute top-10 left-0 right-0 bottom-0 w-full h-[calc(100%-2.5rem)] border-0"
        title={title}
        onLoad={handleIframeLoad}
        allow="clipboard-read; clipboard-write"
        tabIndex={0}
        onMouseDown={focusTerminal}
      />

      {/* Focus hint overlay (fades out) */}
      <div className="absolute bottom-4 right-4 text-xs text-[#666] bg-[#111]/80 px-2 py-1 rounded pointer-events-none animate-[fadeOut_3s_ease-out_forwards]">
        Press F2 (or Ctrl+`) to focus
      </div>

      <style>{`
        @keyframes fadeOut {
          0% { opacity: 1; }
          100% { opacity: 0; }
        }
      `}</style>
    </div>
  );
}
