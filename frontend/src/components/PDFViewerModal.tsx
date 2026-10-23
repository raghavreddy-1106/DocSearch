import React, { useState, useCallback, useRef, useEffect } from 'react';
import {
  X, ChevronLeft, ChevronRight, ZoomIn, ZoomOut,
  RotateCcw, ExternalLink, AlertTriangle, Loader2,
  FileText, Search, Download, Sparkles, Sun, Moon,
  Layers, Square
} from 'lucide-react';

interface PDFViewerModalProps {
  filename: string;
  initialPage: number;
  onClose: () => void;
  searchQuery?: string;
}

type LoadState = 'loading' | 'loaded' | 'error';
type ViewMode = 'single' | 'scroll';
type Theme = 'light' | 'dark';

interface TextPageItem {
  page: number;
  text: string;
}

function HighlightedDocxText({ text, query }: { text: string; query: string }) {
  if (!query || !query.trim()) {
    return <div className="whitespace-pre-wrap leading-relaxed text-sm text-gray-800 font-sans">{text}</div>;
  }
  const terms = query
    .trim()
    .split(/\s+/)
    .filter(t => t.length > 1)
    .map(t => t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!terms.length) {
    return <div className="whitespace-pre-wrap leading-relaxed text-sm text-gray-800 font-sans">{text}</div>;
  }
  const pattern = new RegExp(`(${terms.join('|')})`, 'gi');
  const parts = text.split(pattern);

  return (
    <div className="whitespace-pre-wrap leading-relaxed text-sm text-gray-800 font-sans">
      {parts.map((part, i) =>
        pattern.test(part) ? (
          <mark key={i} className="bg-amber-300 text-gray-950 rounded-xs px-1 font-semibold">
            {part}
          </mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </div>
  );
}

export default function PDFViewerModal({
  filename,
  initialPage,
  onClose,
  searchQuery = '',
}: PDFViewerModalProps) {
  const isPdf = filename.toLowerCase().endsWith('.pdf');
  const [numPages, setNumPages] = useState<number>(0);
  const [currentPage, setCurrentPage] = useState<number>(Math.max(1, initialPage));
  const [scale, setScale] = useState<number>(1.15);
  const [pageLoading, setPageLoading] = useState<boolean>(true);
  const [loadState, setLoadState] = useState<LoadState>('loading');
  const [errorMsg, setErrorMsg] = useState<string>('');
  const [jumpInput, setJumpInput] = useState('');
  const [localQuery, setLocalQuery] = useState(searchQuery);
  const [debouncedQuery, setDebouncedQuery] = useState(searchQuery);
  const [textPages, setTextPages] = useState<TextPageItem[]>([]);
  
  // Theme: Light Mode by default
  const [theme, setTheme] = useState<Theme>('light');
  // View mode: 'single' defaults to exact requested page with vertical scrolling & wheel navigation
  const [viewMode, setViewMode] = useState<ViewMode>('single');

  // Continuous scroll rendered window (starts from currentPage downwards)
  const [renderedPages, setRenderedPages] = useState<number[]>([Math.max(1, initialPage)]);

  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const pageRefs = useRef<{ [key: number]: HTMLDivElement | null }>({});
  const lastWheelTime = useRef<number>(0);

  const fileUrl = `http://localhost:8000/api/v1/documents/file/${encodeURIComponent(filename)}`;
  const contentUrl = `http://localhost:8000/api/v1/documents/content/${encodeURIComponent(filename)}`;
  const infoUrl = `http://localhost:8000/api/v1/documents/info/${encodeURIComponent(filename)}`;

  // Keep currentPage strictly synchronized with initialPage when opened
  useEffect(() => {
    const p = Math.max(1, initialPage);
    setCurrentPage(p);
    setRenderedPages([p, p + 1, p + 2].filter(x => x <= (numPages || 9999)));
  }, [initialPage, filename]);

  // Debounce search query so user can type freely without lagging
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedQuery(localQuery);
    }, 250);
    return () => clearTimeout(timer);
  }, [localQuery]);

  // Load Document Metadata (page count) quickly
  useEffect(() => {
    let cancelled = false;
    fetch(infoUrl)
      .then(res => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
      })
      .then(data => {
        if (cancelled) return;
        if (data.num_pages) {
          setNumPages(data.num_pages);
          setLoadState('loaded');
          // If in scroll mode, initialize pages around current page
          setRenderedPages(prev => {
            const p = currentPage;
            const end = Math.min(data.num_pages, p + 4);
            const list = [];
            for (let i = p; i <= end; i++) list.push(i);
            return list.length ? list : [p];
          });
        }
      })
      .catch(() => {
        if (!cancelled && !isPdf) {
          fetch(contentUrl)
            .then(res => res.json())
            .then(data => {
              if (cancelled) return;
              setTextPages(data.pages || []);
              setNumPages((data.pages || []).length || 1);
              setLoadState('loaded');
            })
            .catch(err => {
              if (cancelled) return;
              setErrorMsg(err.message || 'Failed to load document');
              setLoadState('error');
            });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [infoUrl, contentUrl, isPdf]);

  // For non-PDF documents (DOCX, TXT, CSV), load text content
  useEffect(() => {
    if (isPdf) return;
    let cancelled = false;
    setPageLoading(true);

    fetch(contentUrl)
      .then(res => res.json())
      .then(data => {
        if (cancelled) return;
        const pages: TextPageItem[] = data.pages || [];
        setTextPages(pages);
        setNumPages(pages.length || 1);
        setLoadState('loaded');
        setPageLoading(false);
      })
      .catch(err => {
        if (cancelled) return;
        setErrorMsg(err.message || 'Could not load text content');
        setLoadState('error');
        setPageLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [contentUrl, isPdf]);

  // Preload neighboring pages for high-speed responsiveness
  useEffect(() => {
    if (!isPdf) return;
    const dpi = scale >= 1.5 ? 180 : 150;
    const preloadPages = [currentPage - 1, currentPage + 1, currentPage + 2].filter(p => p >= 1 && (numPages === 0 || p <= numPages));
    preloadPages.forEach(p => {
      const img = new Image();
      img.src = `http://localhost:8000/api/v1/documents/page-image/${encodeURIComponent(filename)}?page=${p}&query=${encodeURIComponent(debouncedQuery)}&dpi=${dpi}`;
    });
  }, [currentPage, numPages, filename, debouncedQuery, scale, isPdf]);

  // Navigate to a specific page
  const goToPage = useCallback((page: number, smooth: boolean = true) => {
    const target = numPages > 0 ? Math.max(1, Math.min(numPages, page)) : Math.max(1, page);
    setCurrentPage(target);
    setPageLoading(true);

    if (viewMode === 'scroll' && isPdf) {
      setRenderedPages(prev => {
        if (!prev.includes(target)) {
          const end = Math.min(numPages || target + 4, target + 4);
          const newPages = [];
          for (let p = target; p <= end; p++) newPages.push(p);
          return newPages;
        }
        return prev;
      });

      setTimeout(() => {
        const el = pageRefs.current[target];
        if (el) {
          el.scrollIntoView({ behavior: smooth ? 'smooth' : 'auto', block: 'start' });
        }
      }, 50);
    } else {
      if (scrollContainerRef.current) {
        scrollContainerRef.current.scrollTo({ top: 0, behavior: smooth ? 'smooth' : 'auto' });
      }
    }
  }, [numPages, viewMode, isPdf]);

  // Handle continuous scroll append when scrolling near bottom
  const handleScroll = (e: React.UIEvent<HTMLDivElement>) => {
    if (viewMode !== 'scroll' || !isPdf || numPages <= 0) return;
    const container = e.currentTarget;
    const threshold = 600;
    if (container.scrollHeight - container.scrollTop - container.clientHeight < threshold) {
      setRenderedPages(prev => {
        const lastPage = prev[prev.length - 1];
        if (lastPage && lastPage < numPages) {
          const nextPages = [...prev];
          for (let i = 1; i <= 3 && lastPage + i <= numPages; i++) {
            if (!nextPages.includes(lastPage + i)) {
              nextPages.push(lastPage + i);
            }
          }
          return nextPages;
        }
        return prev;
      });
    }
  };

  // Mouse wheel scrolling: in single page mode, smoothly advance pages when scrolling at boundaries
  const handleWheel = (e: React.WheelEvent<HTMLDivElement>) => {
    if (viewMode !== 'single') return;
    const now = Date.now();
    if (now - lastWheelTime.current < 450) return; // Debounce wheel page flips

    const container = scrollContainerRef.current;
    if (!container) return;

    // Check if the scroll container is at the boundary
    const isAtBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 15;
    const isAtTop = container.scrollTop <= 5;

    if (e.deltaY > 60 && isAtBottom && currentPage < (numPages || 9999)) {
      lastWheelTime.current = now;
      goToPage(currentPage + 1);
    } else if (e.deltaY < -60 && isAtTop && currentPage > 1) {
      lastWheelTime.current = now;
      goToPage(currentPage - 1);
    }
  };

  const handleJump = (e: React.FormEvent) => {
    e.preventDefault();
    const n = parseInt(jumpInput, 10);
    if (!isNaN(n)) goToPage(n);
    setJumpInput('');
  };

  // Keyboard navigation
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
        return;
      }
      if ((e.key === 'ArrowLeft' || e.key === 'PageUp') && currentPage > 1) {
        goToPage(currentPage - 1);
      }
      if ((e.key === 'ArrowRight' || e.key === 'PageDown') && (numPages === 0 || currentPage < numPages)) {
        goToPage(currentPage + 1);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [currentPage, numPages, goToPage, onClose]);

  const currentTextPage = textPages.find(p => p.page === currentPage) || textPages[currentPage - 1];
  const isLight = theme === 'light';

  return (
    <div
      className={`fixed inset-0 z-50 flex items-center justify-center backdrop-blur-md animate-in fade-in duration-150 ${
        isLight ? 'bg-slate-900/40' : 'bg-black/80'
      }`}
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className={`rounded-2xl shadow-2xl flex flex-col w-[96vw] max-w-6xl h-[95vh] overflow-hidden border transition-colors ${
          isLight
            ? 'bg-white border-slate-200 text-slate-800'
            : 'bg-slate-900 border-slate-700/80 text-white'
        }`}
      >
        {/* ── Top Header Toolbar ── */}
        <div
          className={`flex items-center justify-between px-5 py-3 border-b gap-3 select-none flex-wrap sm:flex-nowrap transition-colors ${
            isLight ? 'bg-white border-slate-200 text-slate-800' : 'bg-slate-950 border-slate-800 text-white'
          }`}
        >
          {/* File Name & Current Page Tag */}
          <div className="flex items-center gap-2.5 min-w-0 flex-1">
            <div className={`p-1.5 rounded-lg flex-shrink-0 ${isLight ? 'bg-blue-50 text-blue-600 border border-blue-200' : 'bg-blue-600/20 text-blue-400 border border-blue-500/30'}`}>
              <FileText size={17} />
            </div>
            <span className={`text-sm truncate font-semibold ${isLight ? 'text-slate-800' : 'text-slate-100'}`} title={filename}>
              {filename}
            </span>
            {numPages > 0 && (
              <span className={`flex-shrink-0 text-xs font-bold px-2.5 py-0.5 rounded-full shadow-xs ${
                isLight ? 'text-blue-700 bg-blue-50 border border-blue-200' : 'text-blue-300 bg-blue-900/60 border border-blue-500/40'
              }`}>
                P.{currentPage} of {numPages}
              </span>
            )}
            <span className={`hidden md:inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded-full ${
              isLight ? 'text-emerald-700 bg-emerald-50 border border-emerald-200' : 'text-emerald-400 bg-emerald-950/60 border border-emerald-500/30'
            }`}>
              <Sparkles size={11} /> Instant Vector View
            </span>
          </div>

          {/* Search Term Highlighting Bar */}
          <div className={`flex items-center gap-2 border rounded-lg px-2.5 py-1.5 w-60 focus-within:ring-1 focus-within:ring-blue-500 transition-all ${
            isLight
              ? 'bg-slate-50 border-slate-300 text-slate-900 focus-within:bg-white focus-within:border-blue-500'
              : 'bg-slate-900 border-slate-700 text-white focus-within:border-blue-500'
          }`}>
            <Search size={14} className={isLight ? 'text-slate-400' : 'text-slate-400'} />
            <input
              type="text"
              value={localQuery}
              onChange={(e) => setLocalQuery(e.target.value)}
              placeholder="Highlight word in page..."
              className="bg-transparent text-xs outline-none w-full placeholder:text-slate-400"
            />
            {localQuery && (
              <button
                onClick={() => setLocalQuery('')}
                className="text-slate-400 hover:text-slate-600 transition-colors"
                title="Clear highlight"
              >
                <X size={13} />
              </button>
            )}
          </div>

          {/* Page Jump Form */}
          {numPages > 1 && (
            <form onSubmit={handleJump} className="flex items-center gap-1">
              <input
                type="number"
                min={1}
                max={numPages}
                value={jumpInput}
                onChange={(e) => setJumpInput(e.target.value)}
                placeholder={`${currentPage}`}
                className={`w-14 text-center text-xs py-1 px-1.5 rounded-lg border outline-none font-medium focus:ring-1 focus:ring-blue-500 ${
                  isLight
                    ? 'bg-slate-50 border-slate-300 text-slate-800 focus:bg-white'
                    : 'bg-slate-900 border-slate-700 text-white'
                }`}
                title="Type page number and press Enter"
              />
              <span className="text-xs text-slate-400">/ {numPages}</span>
            </form>
          )}

          {/* Controls: View Mode, Zoom, Theme, Download, Close */}
          <div className="flex items-center gap-1">
            {/* View Mode Toggle: Continuous Scroll vs Single Page */}
            {isPdf && (
              <button
                onClick={() => {
                  setViewMode(prev => {
                    const nextMode = prev === 'single' ? 'scroll' : 'single';
                    if (nextMode === 'scroll') {
                      setRenderedPages([currentPage, currentPage + 1, currentPage + 2].filter(p => p <= (numPages || 9999)));
                    }
                    return nextMode;
                  });
                }}
                className={`p-1.5 rounded-lg transition-colors border flex items-center gap-1 text-xs font-medium ${
                  isLight
                    ? 'text-slate-700 hover:text-slate-900 hover:bg-slate-100 border-slate-200'
                    : 'text-slate-300 hover:text-white hover:bg-slate-800 border-slate-700'
                }`}
                title={viewMode === 'scroll' ? 'Switch to Single Page Mode' : 'Switch to Continuous Scroll Mode'}
              >
                {viewMode === 'scroll' ? <Layers size={15} className="text-blue-500" /> : <Square size={15} />}
                <span className="hidden xl:inline">{viewMode === 'scroll' ? 'Continuous' : 'Single'}</span>
              </button>
            )}

            {/* Zoom Controls */}
            <button
              onClick={() => setScale(s => Math.max(0.6, Math.round((s - 0.15) * 100) / 100))}
              className={`p-1.5 rounded-lg transition-colors border ${
                isLight ? 'text-slate-700 hover:bg-slate-100 border-slate-200' : 'text-slate-400 hover:text-white hover:bg-slate-800 border-transparent hover:border-slate-700'
              }`}
              title="Zoom out"
            >
              <ZoomOut size={16} />
            </button>

            <span className="text-xs font-semibold px-1 min-w-[3rem] text-center">
              {Math.round(scale * 100)}%
            </span>

            <button
              onClick={() => setScale(s => Math.min(2.5, Math.round((s + 0.15) * 100) / 100))}
              className={`p-1.5 rounded-lg transition-colors border ${
                isLight ? 'text-slate-700 hover:bg-slate-100 border-slate-200' : 'text-slate-400 hover:text-white hover:bg-slate-800 border-transparent hover:border-slate-700'
              }`}
              title="Zoom in"
            >
              <ZoomIn size={16} />
            </button>

            <button
              onClick={() => setScale(1.15)}
              className={`p-1.5 rounded-lg transition-colors border ${
                isLight ? 'text-slate-700 hover:bg-slate-100 border-slate-200' : 'text-slate-400 hover:text-white hover:bg-slate-800 border-transparent hover:border-slate-700'
              }`}
              title="Reset Zoom (100%)"
            >
              <RotateCcw size={14} />
            </button>

            {/* Light / Dark Mode Toggle */}
            <button
              onClick={() => setTheme(prev => prev === 'light' ? 'dark' : 'light')}
              className={`p-1.5 rounded-lg transition-colors border ${
                isLight ? 'text-amber-600 hover:bg-amber-50 border-slate-200' : 'text-amber-400 hover:bg-slate-800 border-slate-700'
              }`}
              title={isLight ? 'Switch to Dark Mode' : 'Switch to Light Mode'}
            >
              {isLight ? <Moon size={16} /> : <Sun size={16} />}
            </button>

            {/* Direct Document Download Link */}
            <a
              href={fileUrl}
              download={filename}
              className={`p-1.5 rounded-lg transition-colors border ${
                isLight ? 'text-slate-700 hover:bg-slate-100 border-slate-200' : 'text-slate-400 hover:text-white hover:bg-slate-800 border-transparent hover:border-slate-700'
              }`}
              title="Download original document"
            >
              <Download size={16} />
            </a>

            {/* Close Button */}
            <button
              onClick={onClose}
              className="p-1.5 text-slate-400 hover:text-white hover:bg-red-600 rounded-lg transition-colors ml-1"
              title="Close modal (Esc)"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* ── Main Scrollable Page Canvas ── */}
        <div
          ref={scrollContainerRef}
          onScroll={handleScroll}
          onWheel={handleWheel}
          className={`flex-1 overflow-y-auto overflow-x-auto p-6 flex flex-col items-center justify-start relative select-text transition-colors ${
            isLight ? 'bg-slate-100/90' : 'bg-slate-950'
          }`}
          style={{ scrollBehavior: 'smooth' }}
        >
          {/* Floating Subtle Page Loading Indicator */}
          {pageLoading && (
            <div className={`absolute top-4 left-1/2 -translate-x-1/2 z-30 px-3.5 py-1.5 rounded-full shadow-xl border flex items-center gap-2 text-xs backdrop-blur-md animate-in fade-in ${
              isLight ? 'bg-white/95 text-slate-800 border-slate-200' : 'bg-slate-900/90 text-white border-slate-700/80'
            }`}>
              <Loader2 size={13} className="animate-spin text-blue-500" />
              <span>Rendering page {currentPage}...</span>
            </div>
          )}

          {/* Error State */}
          {loadState === 'error' && (
            <div className={`flex flex-col items-center justify-center my-auto max-w-sm text-center p-6 rounded-xl border ${
              isLight ? 'bg-white border-red-200 shadow-md' : 'bg-slate-900 border-red-500/40'
            }`}>
              <AlertTriangle size={36} className="text-red-500 mb-3" />
              <h3 className={`font-semibold mb-2 ${isLight ? 'text-slate-800' : 'text-white'}`}>Could Not Open Page</h3>
              <p className="text-xs text-slate-500 mb-4">{errorMsg}</p>
              <a
                href={fileUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-blue-600 hover:underline flex items-center gap-1 font-medium"
              >
                <ExternalLink size={13} /> Open raw document directly
              </a>
            </div>
          )}

          {/* ── Mode 1: PDF Rendering in Single-Page Mode (Direct & Instant) ── */}
          {isPdf && loadState !== 'error' && viewMode === 'single' && (
            <div
              className={`transition-transform duration-100 ease-out relative rounded-xs overflow-hidden bg-white mb-6 ${
                isLight ? 'shadow-xl border border-slate-200' : 'shadow-2xl border border-slate-700'
              }`}
              style={{
                width: `${Math.round(680 * scale)}px`,
                maxWidth: '100%',
              }}
            >
              {/* Top Page Watermark Badge */}
              <div className={`absolute top-3 right-3 z-10 backdrop-blur-md text-[11px] font-bold px-2.5 py-1 rounded shadow-md border select-none flex items-center gap-1.5 ${
                isLight
                  ? 'bg-white/95 text-slate-800 border-slate-200 shadow-xs'
                  : 'bg-slate-950/80 text-white border-slate-700/60'
              }`}>
                <FileText size={12} className="text-blue-500" />
                Page {currentPage} of {numPages || '...'}
              </div>

              <img
                key={`${filename}-${currentPage}-${debouncedQuery}`}
                src={`http://localhost:8000/api/v1/documents/page-image/${encodeURIComponent(filename)}?page=${currentPage}&query=${encodeURIComponent(debouncedQuery)}&dpi=${scale >= 1.5 ? 180 : 150}`}
                alt={`Page ${currentPage} of ${filename}`}
                onLoad={() => {
                  setPageLoading(false);
                  setLoadState('loaded');
                }}
                onError={() => {
                  setPageLoading(false);
                  setErrorMsg('Failed to render page image from document.');
                  setLoadState('error');
                }}
                className="w-full h-auto block select-none bg-white min-h-[500px]"
                loading="eager"
              />
            </div>
          )}

          {/* ── Mode 2: PDF Rendering with Continuous Scrolling ── */}
          {isPdf && loadState !== 'error' && viewMode === 'scroll' && (
            <div className="flex flex-col items-center gap-6 w-full pb-10">
              {renderedPages.map((pageNum) => {
                const imgUrl = `http://localhost:8000/api/v1/documents/page-image/${encodeURIComponent(filename)}?page=${pageNum}&query=${encodeURIComponent(debouncedQuery)}&dpi=${scale >= 1.5 ? 180 : 150}`;
                return (
                  <div
                    key={pageNum}
                    data-page={pageNum}
                    ref={(el) => {
                      pageRefs.current[pageNum] = el;
                    }}
                    className={`transition-transform duration-100 ease-out relative rounded-xs overflow-hidden bg-white ${
                      isLight ? 'shadow-xl border border-slate-200' : 'shadow-2xl border border-slate-700'
                    }`}
                    style={{
                      width: `${Math.round(680 * scale)}px`,
                      maxWidth: '100%',
                    }}
                  >
                    {/* Top Page Watermark Badge */}
                    <div className={`absolute top-3 right-3 z-10 backdrop-blur-md text-[11px] font-bold px-2.5 py-1 rounded shadow-md border select-none flex items-center gap-1.5 ${
                      isLight
                        ? 'bg-white/95 text-slate-800 border-slate-200 shadow-xs'
                        : 'bg-slate-950/80 text-white border-slate-700/60'
                    }`}>
                      <FileText size={12} className="text-blue-500" />
                      Page {pageNum} of {numPages || '...'}
                    </div>

                    <img
                      src={imgUrl}
                      alt={`Page ${pageNum} of ${filename}`}
                      onLoad={() => {
                        if (pageNum === currentPage) {
                          setPageLoading(false);
                          setLoadState('loaded');
                        }
                      }}
                      className="w-full h-auto block select-none bg-white min-h-[500px]"
                      loading="lazy"
                    />
                  </div>
                );
              })}
            </div>
          )}

          {/* ── Mode 3: Non-PDF Document Rendering (DOCX, TXT, CSV) ── */}
          {!isPdf && loadState === 'loaded' && currentTextPage && (
            <div
              className={`shadow-xl rounded-xl p-10 border relative max-w-3xl w-full mb-6 ${
                isLight ? 'bg-white border-slate-200 text-slate-900' : 'bg-slate-900 border-slate-700 text-slate-100'
              }`}
              style={{
                fontSize: `${Math.round(14 * (scale / 1.15))}px`,
                minHeight: Math.round(750 * (scale / 1.15)),
              }}
            >
              <div className={`absolute top-3 right-4 border text-[10px] font-bold px-2.5 py-0.5 rounded shadow-xs select-none ${
                isLight ? 'bg-slate-100 text-slate-700 border-slate-200' : 'bg-slate-800 text-slate-300 border-slate-700'
              }`}>
                PAGE {currentPage} OF {numPages}
              </div>
              <HighlightedDocxText text={currentTextPage.text} query={localQuery} />
            </div>
          )}
        </div>

        {/* ── Bottom Navigation Footer ── */}
        <div
          className={`flex items-center justify-between px-6 py-2.5 border-t select-none text-xs transition-colors ${
            isLight
              ? 'bg-white border-slate-200 text-slate-600'
              : 'bg-slate-950 border-slate-800 text-slate-300'
          }`}
        >
          <button
            onClick={() => goToPage(currentPage - 1)}
            disabled={currentPage <= 1}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 font-semibold rounded-lg border transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
              isLight
                ? 'border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-800 shadow-xs'
                : 'border-slate-700 bg-slate-900 hover:bg-slate-800 text-white'
            }`}
          >
            <ChevronLeft size={15} /> Previous Page
          </button>

          <div className="flex items-center gap-3">
            <span className="hidden sm:inline text-slate-400">
              Flip pages with <kbd className={`px-1.5 py-0.5 border rounded text-[10px] font-mono ${
                isLight ? 'bg-slate-100 border-slate-200 text-slate-600' : 'bg-slate-800 border-slate-700 text-slate-300'
              }`}>←</kbd> and <kbd className={`px-1.5 py-0.5 border rounded text-[10px] font-mono ${
                isLight ? 'bg-slate-100 border-slate-200 text-slate-600' : 'bg-slate-800 border-slate-700 text-slate-300'
              }`}>→</kbd> or scroll with wheel
            </span>
            <span className={`font-semibold px-2.5 py-0.5 rounded border ${
              isLight
                ? 'text-blue-700 bg-blue-50 border-blue-200'
                : 'text-blue-400 bg-blue-950/80 border-blue-800/50'
            }`}>
              Page {currentPage} / {numPages || '...'}
            </span>
          </div>

          <button
            onClick={() => goToPage(currentPage + 1)}
            disabled={numPages > 0 && currentPage >= numPages}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 font-semibold rounded-lg border transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${
              isLight
                ? 'border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-800 shadow-xs'
                : 'border-slate-700 bg-slate-900 hover:bg-slate-800 text-white'
            }`}
          >
            Next Page <ChevronRight size={15} />
          </button>
        </div>

      </div>
    </div>
  );
}
