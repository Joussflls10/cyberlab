import { useEffect, useState, useRef, useCallback } from 'react';

interface TerminalProps {
  port: number | null;
  onFocus?: () => void;
}

type Status = 'waiting' | 'connecting' | 'connected' | 'disconnected' | 'error';

export default function Terminal({ port, onFocus }: TerminalProps) {
  const [status, setStatus] = useState<Status>('waiting');
  const [showReconnect, setShowReconnect] = useState(false);
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const focusShortcutRegistered = useRef(false);

  // Register keyboard shortcut (Ctrl+`) to focus terminal
  useEffect(() => {
    if (focusShortcutRegistered.current) return;
    focusShortcutRegistered.current = true;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.key === '`') {
        e.preventDefault();
        if (iframeRef.current && status === 'connected') {
          iframeRef.current.focus();
          onFocus?.();
        }
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [status, onFocus]);

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
  };

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
    <div className="absolute top-3 right-3 z-10 flex items-center gap-2 px-3 py-1.5 bg-[#111]/90 backdrop-blur-sm rounded border border-[#333]">
      <div
        className="w-2 h-2 rounded-full animate-pulse"
        style={{ backgroundColor: getStatusColor() }}
      />
      <span className="text-xs font-mono" style={{ color: getStatusColor() }}>
        {getStatusText()}
      </span>
      {showReconnect && (
        <button
          onClick={handleReconnect}
          className="ml-2 px-2 py-0.5 text-xs bg-[#333] hover:bg-[#444] rounded transition-colors"
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
      className="relative h-full bg-[#0a0a0a]"
      style={{ fontFamily: 'JetBrains Mono, monospace' }}
    >
      <StatusIndicator />
      
      {/* Terminal header bar */}
      <div className="absolute top-0 left-0 right-16 h-8 bg-[#111] border-b border-[#222] flex items-center px-3">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded-full bg-[#ff4444]" />
          <div className="w-3 h-3 rounded-full bg-[#ffaa00]" />
          <div className="w-3 h-3 rounded-full bg-[#00ff88]" />
        </div>
        <span className="ml-4 text-xs text-[#666]">ttyd — {port}</span>
      </div>

      <iframe
        ref={iframeRef}
        src={`http://localhost:${port}`}
        className="absolute top-8 left-0 right-0 bottom-0 w-full h-[calc(100%-2rem)] border-0"
        title="Terminal"
        onLoad={handleIframeLoad}
        allow="clipboard-read; clipboard-write"
      />

      {/* Focus hint overlay (fades out) */}
      <div className="absolute bottom-4 right-4 text-xs text-[#666] bg-[#111]/80 px-2 py-1 rounded pointer-events-none animate-[fadeOut_3s_ease-out_forwards]">
        Ctrl+` to focus
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
