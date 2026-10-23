import React, { useState, useRef, useEffect } from 'react';
import {
  Search, FileText, AlertTriangle, Info,
  ChevronDown, ChevronUp, Database, Loader2, BookOpen,
  AlertCircle, List, Sparkles, ExternalLink, Eye,
  Globe, BookMarked, ChevronRight, Cpu, Check, Zap, Clock
} from 'lucide-react';
import clsx from 'clsx';
import { useApp } from '../lib/AppContext';
import { useAuth } from '../lib/AuthContext';
import type { QueryResponse, SearchPageResult, ModelInfo } from '../lib/AppContext';
import { useNavigate } from 'react-router-dom';
import PDFViewerModal from '../components/PDFViewerModal';

interface PDFTarget {
  filename: string;
  page: number;
}

interface AIAnswerSource {
  title: string;
  authors: string[];
  year?: number | string;
  venue?: string;
  doi?: string;
  url?: string;
}

interface AIAnswerResult {
  answer: string;
  sources: AIAnswerSource[];
  status: string;
  model_used: string;
  query: string;
}

// ── Page Badge (clickable) ───────────────────────────────────────────────────
function PageBadge({
  page,
  document: doc,
  onClick,
}: {
  page: number;
  document: string;
  onClick: (target: PDFTarget) => void;
}) {
  return (
    <button
      onClick={() => onClick({ filename: doc, page })}
      title={`Open ${doc} at page ${page}`}
      className="inline-flex items-center gap-1 text-xs font-bold text-primary-accent bg-blue-50 border border-blue-200 px-2 py-0.5 rounded hover:bg-blue-100 hover:border-blue-400 transition-all cursor-pointer group"
    >
      <Eye size={10} className="opacity-0 group-hover:opacity-100 transition-opacity" />
      P.{page}
    </button>
  );
}

// ── Highlighted snippet ──────────────────────────────────────────────────────
function HighlightedSnippet({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <span>
      {parts.map((part, i) => {
        if (part.startsWith('**') && part.endsWith('**')) {
          return (
            <mark key={i} className="bg-yellow-100 text-yellow-900 px-0.5 rounded font-semibold not-italic">
              {part.slice(2, -2)}
            </mark>
          );
        }
        return <span key={i}>{part}</span>;
      })}
    </span>
  );
}

// ── Markdown-like text renderer ──────────────────────────────────────────────
function MarkdownText({ text }: { text: string }) {
  const lines = text.split('\n');
  return (
    <div className="space-y-2">
      {lines.map((line, i) => {
        if (!line.trim()) return <div key={i} className="h-1" />;
        // Bold headings: **text**
        const rendered = line.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
        // Italic: *text*
        const rendered2 = rendered.replace(/\*([^*]+)\*/g, '<em>$1</em>');
        return (
          <p
            key={i}
            className="text-sm text-primary-text leading-relaxed"
            dangerouslySetInnerHTML={{ __html: rendered2 }}
          />
        );
      })}
    </div>
  );
}

// ── Page result card ─────────────────────────────────────────────────────────
function PageResultCard({
  result,
  onPageClick,
}: {
  result: SearchPageResult;
  onPageClick: (target: PDFTarget) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const showCount = expanded ? result.snippets.length : Math.min(2, result.snippets.length);

  return (
    <div className="border border-border rounded-lg bg-white overflow-hidden hover:border-blue-200 hover:shadow-sm transition-all">
      <div className="flex items-center justify-between px-4 py-2.5 bg-gray-50/60 border-b border-border">
        <div className="flex items-center gap-2">
          <PageBadge page={result.page} document={result.document} onClick={onPageClick} />
          <span className="text-xs text-secondary-text truncate max-w-[220px]">{result.document}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-secondary-text whitespace-nowrap">
            {result.match_count} match{result.match_count !== 1 ? 'es' : ''}
          </span>
          <button
            onClick={() => onPageClick({ filename: result.document, page: result.page })}
            title="Open this page"
            className="text-[10px] text-primary-accent border border-blue-200 rounded px-1.5 py-0.5 hover:bg-blue-50 transition-colors flex items-center gap-1"
          >
            <ExternalLink size={10} /> View page
          </button>
        </div>
      </div>
      <div className="p-4 space-y-2">
        {result.snippets.slice(0, showCount).map((snip, i) => (
          <p key={i} className="text-xs text-primary-text leading-relaxed border-l-2 border-primary-accent/30 pl-3 italic">
            "<HighlightedSnippet text={snip} />"
          </p>
        ))}
        {result.snippets.length > 2 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-primary-accent hover:underline flex items-center gap-1 mt-1"
          >
            {expanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
            {expanded ? 'Show less' : `+${result.snippets.length - 2} more passages`}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Model Switcher Dropdown ───────────────────────────────────────────────────
function ModelSwitcher({
  models,
  currentModel,
  onSwitch,
  isSwitching,
}: {
  models: ModelInfo[];
  currentModel: string;
  onSwitch: (modelId: string) => void;
  isSwitching: boolean;
}) {
  const [open, setOpen] = useState(false);
  const current = models.find(m => m.id === currentModel) || models[0];
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(o => !o)}
        disabled={isSwitching}
        className="flex items-center gap-2 bg-surface border border-border rounded-md px-3 py-2 text-xs font-medium text-primary-text hover:border-primary-accent hover:bg-blue-50/30 transition-all shadow-sm w-full"
      >
        <span className="text-sm">{current?.icon || '⚡'}</span>
        <span className="flex-1 text-left truncate">
          {isSwitching ? 'Switching...' : (current?.name || currentModel)}
        </span>
        <ChevronDown size={12} className={clsx('transition-transform flex-shrink-0', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute top-full left-0 right-0 mt-1 bg-white border border-border rounded-lg shadow-xl z-50 overflow-hidden max-h-96 overflow-y-auto">
          {/* Gemini group */}
          <div className="px-3 py-1.5 bg-blue-50 border-b border-border">
            <p className="text-[9px] font-bold text-blue-700 uppercase tracking-widest">🔷 Google Gemini</p>
          </div>
          {models.filter(m => (m as any).group === 'gemini' || m.id.startsWith('gemini')).map(m => (
            <button
              key={m.id}
              onClick={() => { onSwitch(m.id); setOpen(false); }}
              className={clsx(
                "w-full flex items-start gap-2.5 px-3 py-2 hover:bg-blue-50 transition-colors text-left",
                m.id === currentModel && "bg-blue-50/70"
              )}
            >
              <span className="text-sm leading-none mt-0.5">{m.icon}</span>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-primary-text flex items-center gap-1">
                  {m.name}
                  {m.id === currentModel && <Check size={10} className="text-green-500" />}
                </p>
                <p className="text-[10px] text-secondary-text mt-0.5 truncate">{m.description}</p>
              </div>
            </button>
          ))}
          {/* Search / Web / Academic group */}
          <div className="px-3 py-1.5 bg-violet-50 border-y border-border">
            <p className="text-[9px] font-bold text-violet-700 uppercase tracking-widest">🔍 AI Search Providers</p>
          </div>
          {models.filter(m => (m as any).group === 'search' || !m.id.startsWith('gemini')).map(m => (
            <button
              key={m.id}
              onClick={() => { onSwitch(m.id); setOpen(false); }}
              className={clsx(
                "w-full flex items-start gap-2.5 px-3 py-2 hover:bg-violet-50 transition-colors text-left",
                m.id === currentModel && "bg-violet-50/70"
              )}
            >
              <span className="text-sm leading-none mt-0.5">{m.icon}</span>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-primary-text flex items-center gap-1">
                  {m.name}
                  {m.id === currentModel && <Check size={10} className="text-green-500" />}
                </p>
                <p className="text-[10px] text-secondary-text mt-0.5 truncate">{m.description}</p>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── AI Answer Panel ───────────────────────────────────────────────────────────
function AIAnswerPanel({ result, onPageClick }: { result: AIAnswerResult; onPageClick?: (target: PDFTarget) => void }) {
  const isMistral = result.model_used.includes('mistral');
  const isGemini = result.model_used.startsWith('gemini');
  const isTavily = result.model_used === 'tavily';
  const isOpenAlex = result.model_used === 'openalex';
  const isOllama = !isMistral && !isGemini && !isTavily && !isOpenAlex;

  return (
    <div className="p-6 space-y-5">
      {/* Header */}
      <div className="flex items-center gap-2.5">
        <div className={clsx(
          "w-8 h-8 rounded-full flex items-center justify-center shadow-sm text-white",
          isMistral ? "bg-gradient-to-br from-amber-500 to-orange-600" :
          isGemini ? "bg-gradient-to-br from-blue-500 to-indigo-600" :
          isTavily ? "bg-gradient-to-br from-cyan-500 to-teal-600" :
          isOpenAlex ? "bg-gradient-to-br from-violet-500 to-purple-600" :
          "bg-gradient-to-br from-emerald-500 to-teal-600"
        )}>
          {isMistral ? <span className="text-sm">🌊</span> :
           isGemini ? <Sparkles size={16} /> :
           isTavily ? <Globe size={16} /> :
           isOpenAlex ? <BookMarked size={16} /> :
           <span className="text-base">🦙</span>}
        </div>
        <div>
          <h2 className="text-base font-bold text-primary-text">
            {isMistral ? 'Mistral AI Answer' :
             isGemini ? 'Gemini AI Answer' :
             isTavily ? 'Web Search AI Answer' :
             isOpenAlex ? 'Academic Literature Answer' :
             'Ollama Document Intelligence'}
          </h2>
          <p className="text-[10px] text-secondary-text">
            Provider: <span className="font-semibold text-primary-text">
              {isMistral ? 'Mistral AI' :
               isGemini ? 'Google Gemini' :
               isTavily ? 'Tavily Search' :
               isOpenAlex ? 'OpenAlex' :
               'Ollama (Local LLM & RAG)'}
            </span>
            {' · '}Model: <span className="font-mono text-primary-accent">{result.model_used}</span>
          </p>
        </div>
      </div>

      {/* Answer Box */}
      <div className={clsx(
        "rounded-xl p-5 shadow-sm border",
        isMistral ? "bg-gradient-to-br from-amber-50/60 to-orange-50/60 border-amber-200" :
        isGemini ? "bg-gradient-to-br from-blue-50/60 to-indigo-50/60 border-blue-200" :
        isTavily ? "bg-gradient-to-br from-cyan-50/60 to-teal-50/60 border-cyan-200" :
        isOpenAlex ? "bg-gradient-to-br from-violet-50/60 to-purple-50/60 border-violet-200" :
        "bg-gradient-to-br from-emerald-50/60 to-teal-50/60 border-emerald-200"
      )}>
        {result.status === 'NO_RESULTS' || result.status === 'NO_EVIDENCE' ? (
          <div className="flex items-start gap-3 text-amber-800">
            <AlertCircle size={18} className="text-amber-500 mt-0.5 flex-shrink-0" />
            <p className="text-sm leading-relaxed">{result.answer}</p>
          </div>
        ) : (
          <MarkdownText text={result.answer} />
        )}
      </div>

      {/* Sources (for Tavily, OpenAlex, and Ollama PDF citations) */}
      {result.sources && result.sources.length > 0 && (
        <div>
          <h3 className="text-xs font-bold text-secondary-text uppercase tracking-wider mb-3 flex items-center gap-1.5">
            {isOpenAlex ? <BookMarked size={12} /> : isTavily ? <Globe size={12} /> : <BookOpen size={12} />}
            {isOpenAlex ? `Academic Sources (${result.sources.length})` :
             isTavily ? `Web Sources (${result.sources.length})` :
             `Verified Document Sources (${result.sources.length})`}
          </h3>
          <div className="space-y-2">
            {result.sources.map((src, i) => {
              const pageMatch = src.title.match(/Page\s+(\d+)/i);
              const pageNum = pageMatch ? parseInt(pageMatch[1], 10) : 1;
              const docName = src.venue || src.title.split(' — ')[0];

              return (
                <div
                  key={i}
                  className="flex items-start gap-3 p-3 bg-white border border-border rounded-lg hover:border-primary-accent/40 hover:shadow-sm transition-all"
                >
                  <span className="flex-shrink-0 w-5 h-5 rounded-full bg-gray-100 text-secondary-text text-[10px] font-bold flex items-center justify-center mt-0.5">
                    {i + 1}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-primary-text leading-snug">
                      {src.url ? (
                        <a
                          href={src.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="hover:text-primary-accent hover:underline inline-flex items-center gap-1"
                        >
                          {src.title}
                          <ExternalLink size={9} className="flex-shrink-0" />
                        </a>
                      ) : (
                        <span>{src.title}</span>
                      )}
                    </p>
                    {isOllama && onPageClick && (
                      <div className="mt-1 flex items-center gap-2">
                        <PageBadge page={pageNum} document={docName} onClick={onPageClick} />
                        <span className="text-[10px] text-gray-400">Click to view in document viewer</span>
                      </div>
                    )}
                    {(src.authors && src.authors.length > 0) || (src.venue && !isOllama) ? (
                      <p className="text-[10px] text-secondary-text mt-0.5">
                        {src.authors && src.authors.length > 0 && (
                          <>{src.authors.slice(0, 2).join(', ')}{src.authors.length > 2 && ' et al.'} · </>
                        )}
                        {src.year && <>{src.year} · </>}
                        {src.venue && !isOllama && <span>{src.venue}</span>}
                      </p>
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Footer */}
      <p className="text-[10px] text-secondary-text border-t border-border pt-3">
        {isMistral ? (
          <>Powered by <a href="https://mistral.ai" target="_blank" rel="noopener noreferrer" className="text-amber-600 hover:underline font-medium">Mistral AI</a> — {result.model_used}</>
        ) : isTavily ? (
          <>Powered by <a href="https://tavily.com" target="_blank" rel="noopener noreferrer" className="text-cyan-600 hover:underline font-medium">Tavily Search</a> — real-time web intelligence</>  
        ) : isOpenAlex ? (
          <>Powered by <a href="https://openalex.org" target="_blank" rel="noopener noreferrer" className="text-violet-600 hover:underline font-medium">OpenAlex</a> — 250M+ scholarly research papers</>  
        ) : isGemini ? (
          <>Powered by <span className="font-semibold text-primary-accent">Google Gemini ({result.model_used})</span> — Direct General Knowledge AI</>
        ) : (
          <>Powered by <span className="font-semibold text-emerald-600">Local Ollama ({result.model_used})</span> — Grounded strictly in your uploaded PDF</>
        )}
      </p>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function AnalyzeWorkspace() {
  const {
    documentCount, activeDocuments,
    savedQuery, setSavedQuery,
    savedResponse, setSavedResponse,
    savedActiveTab, setSavedActiveTab,
    selectedModel, setSelectedModel,
    models, isSwitchingModel
  } = useApp();
  const { user, getAuthHeaders } = useAuth();
  const navigate = useNavigate();

  const query = savedQuery;
  const setQuery = setSavedQuery;
  const response = savedResponse;
  const setResponse = setSavedResponse;
  const activeTab = savedActiveTab;
  const setActiveTab = setSavedActiveTab;

  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [userSearches, setUserSearches] = useState<any[]>([]);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // PDF viewer state
  const [pdfTarget, setPdfTarget] = useState<PDFTarget | null>(null);

  // AI Answer state
  const [aiAnswer, setAiAnswer] = useState<AIAnswerResult | null>(null);
  const [isAiLoading, setIsAiLoading] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const loadUserHistory = () => {
    fetch('http://localhost:8000/api/v1/history/search?limit=15', {
      headers: getAuthHeaders()
    })
      .then(r => r.json())
      .then(d => {
        if (d && Array.isArray(d.history)) {
          setUserSearches(d.history);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    loadUserHistory();
  }, [user]);

  const openPage = (target: PDFTarget) => {
    setPdfTarget(target);
  };

  const isMistralModel = selectedModel.includes('mistral');
  const isGeminiModel = selectedModel.startsWith('gemini');
  const isTavilyModel = selectedModel === 'tavily';
  const isOpenAlexModel = selectedModel === 'openalex';

  const activeModelObj = models.find(m => m.id === selectedModel);
  const activeModelName = activeModelObj?.name || selectedModel;

  const handleSubmit = async (e?: React.FormEvent, customQuery?: string) => {
    if (e) e.preventDefault();
    const q = (customQuery !== undefined ? customQuery : query).trim();
    if (!q) return;

    if (customQuery !== undefined) {
      setQuery(customQuery);
    }

    setIsLoading(true);
    setIsAiLoading(true);
    setResponse(null);
    setError(null);
    setAiAnswer(null);
    setAiError(null);
    setActiveTab('pdf-answer');

    // ── Single Authoritative Search & RAG Generation ───────────────────────
    fetch('http://localhost:8000/api/v1/query/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...getAuthHeaders()
      },
      body: JSON.stringify({
        query: q,
        documentNames: activeDocuments && activeDocuments.length > 0 ? activeDocuments : null,
        user_id: user?.id,
        user_email: user?.email
      })
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Server error: ${res.status}`);
        const data: QueryResponse = await res.json();
        setResponse(data);
        // Authoritative synchronization: Local AI Answer uses the exact same verified result
        setAiAnswer({
          answer: data.answer,
          sources: (data as any).sources || [],
          status: data.status,
          model_used: data.diagnostics?.model_used || selectedModel,
          query: q,
        });
        if (data.status === 'ABSTAINED' && data.search_results && data.search_results.total_pages > 0) {
          setActiveTab('pages');
        }
        loadUserHistory();
      })
      .catch((err) => {
        setError(err.message || 'Failed to connect to DocSearch backend.');
        setAiError(err.message || 'Failed to connect to DocSearch backend.');
      })
      .finally(() => {
        setIsLoading(false);
        setIsAiLoading(false);
      });
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  if (documentCount === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-12rem)] max-w-lg mx-auto text-center">
        <div className="w-16 h-16 bg-gray-100 text-gray-400 rounded-full flex items-center justify-center mb-6">
          <Database size={32} />
        </div>
        <h2 className="text-xl font-bold text-primary-text mb-2">No documents indexed</h2>
        <p className="text-sm text-secondary-text mb-6">
          Upload and index PDF documents before running searches or AI analysis.
        </p>
        <button
          onClick={() => navigate('/documents')}
          className="bg-primary-accent text-white px-5 py-2.5 rounded-md text-sm font-medium hover:bg-blue-600 transition-colors shadow-sm"
        >
          Go to Documents
        </button>
      </div>
    );
  }

  const sr = response?.search_results;
  const hasSearchResults = sr && (sr.results.length > 0 || (sr.related_results && sr.related_results.length > 0));
  const hasEvidence = response?.evidence && response.evidence.length > 0;

  return (
    <>
      {/* ── PDF Viewer Modal ── */}
      {pdfTarget && (
        <PDFViewerModal
          filename={pdfTarget.filename}
          initialPage={pdfTarget.page}
          searchQuery={query.trim()}
          onClose={() => setPdfTarget(null)}
        />
      )}

      <div className="h-[calc(100vh-8rem)] flex gap-6">

        {/* ── LEFT: Query Panel ── */}
        <div className="w-72 flex flex-col gap-4 flex-shrink-0">
          <div className="bg-surface border border-border rounded-lg p-5 shadow-sm flex flex-col h-full gap-4">

            {/* Active document indicator */}
            {activeDocuments && activeDocuments.length > 0 && (
              <div className="bg-blue-50 border border-blue-100 rounded-md p-3">
                <span className="text-[10px] font-bold text-primary-accent uppercase tracking-wider block mb-1">Searching in:</span>
                {activeDocuments.map((doc, i) => (
                  <span key={i} className="text-xs font-medium text-primary-text flex items-center gap-1.5 truncate">
                    <FileText size={11} className="text-primary-accent flex-shrink-0" />
                    {doc}
                  </span>
                ))}
              </div>
            )}

            {/* Model Switcher */}
            {models.length > 0 && (
              <div>
                <label className="text-[10px] font-bold text-secondary-text uppercase tracking-wider block mb-1.5">
                  AI Model
                </label>
                <ModelSwitcher
                  models={models}
                  currentModel={selectedModel}
                  onSwitch={setSelectedModel}
                  isSwitching={isSwitchingModel}
                />
              </div>
            )}

            <form onSubmit={handleSubmit} className="flex flex-col gap-3">
              <label className="text-sm font-medium text-primary-text">
                Search or ask a question
              </label>
              <textarea
                ref={textareaRef}
                className="w-full bg-gray-50 border border-border rounded-md p-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary-accent/20 focus:border-primary-accent resize-none h-32 transition-all"
                placeholder={'Enter your search query or question...'}
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
              />

              <div className="flex items-center justify-between mt-1">
                <span className="text-xs text-secondary-text flex items-center gap-1">
                  <Info size={11} /> Enter to search
                </span>
                <button
                  type="submit"
                  disabled={isLoading || !query.trim()}
                  className="bg-primary-text text-white px-4 py-2 rounded-md text-sm font-medium hover:bg-gray-800 transition-colors disabled:opacity-50 flex items-center gap-2"
                >
                  {isLoading ? (
                    <><Loader2 size={14} className="animate-spin" /> Searching</>
                  ) : (
                    <><Search size={14} /> Search</>
                  )}
                </button>
              </div>
            </form>

            {/* Search stats */}
            {response && sr && (
              <div className="p-3 bg-gray-50 border border-border rounded-md">
                <p className="text-[10px] font-bold text-secondary-text uppercase tracking-wider mb-2">Search Summary</p>
                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <p className="text-xl font-bold text-primary-text">{sr.total_pages}</p>
                    <p className="text-[10px] text-secondary-text">matching pages</p>
                  </div>
                  <div>
                    <p className="text-xl font-bold text-primary-text">{sr.total_matches}</p>
                    <p className="text-[10px] text-secondary-text">{sr.mode === 'semantic_match' ? 'semantic matches' : 'exact matches'}</p>
                  </div>
                </div>
                <p className="text-[10px] text-secondary-text mt-2">
                  Mode: <span className="font-semibold text-primary-accent capitalize">{sr.mode.replace(/_/g, ' ')}</span>
                </p>
              </div>
            )}

            {response && response.status === 'ABSTAINED' && (
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-md">
                <div className="flex items-start gap-2">
                  <AlertCircle size={14} className="text-amber-600 mt-0.5 flex-shrink-0" />
                  <p className="text-xs text-amber-800">No relevant content found in the selected document(s).</p>
                </div>
              </div>
            )}

            {/* Hint about clicking page badges */}
            {hasSearchResults && (
              <div className="p-2.5 bg-blue-50 border border-blue-100 rounded-md">
                <p className="text-[10px] text-blue-700 flex items-center gap-1">
                  <Eye size={10} /> Click any <strong>P.XX</strong> badge to open that page
                </p>
              </div>
            )}

            {/* User's recent search activities */}
            <div className="flex-1 flex flex-col min-h-0 pt-3 border-t border-border mt-1">
              <div className="flex items-center justify-between mb-2">
                <span className="text-[10px] font-bold text-secondary-text uppercase tracking-wider flex items-center gap-1.5">
                  <Clock size={11} className="text-primary-accent" />
                  My Search Activity
                </span>
                <span className="text-[10px] font-semibold text-gray-400">
                  {userSearches.length} saved
                </span>
              </div>
              <div className="flex-1 overflow-y-auto space-y-1.5 pr-1 max-h-52">
                {userSearches.length === 0 ? (
                  <p className="text-[11px] text-gray-400 italic py-2 text-center">
                    No searches yet. Your searches will be stored here.
                  </p>
                ) : (
                  userSearches.map((item, idx) => (
                    <button
                      key={item.id || idx}
                      type="button"
                      onClick={() => {
                        handleSubmit(undefined, item.query);
                      }}
                      className="w-full text-left p-2 rounded-lg bg-gray-50 hover:bg-blue-50/80 border border-border/80 hover:border-blue-200 transition-all cursor-pointer group flex items-center justify-between"
                      title={`Search again: "${item.query}"`}
                    >
                      <div className="min-w-0 flex-1">
                        <p className="text-xs text-primary-text font-medium truncate group-hover:text-primary-accent">
                          {item.query}
                        </p>
                        <p className="text-[10px] text-secondary-text flex items-center gap-1.5 mt-0.5">
                          <span className={clsx(
                            "w-1.5 h-1.5 rounded-full inline-block",
                            item.status === 'SUCCESS' ? "bg-emerald-500" : "bg-amber-500"
                          )} />
                          <span>{item.result_pages > 0 ? `${item.result_pages} pages` : 'No results'}</span>
                        </p>
                      </div>
                      <ChevronRight size={12} className="text-gray-300 group-hover:text-primary-accent group-hover:translate-x-0.5 transition-all flex-shrink-0 ml-1" />
                    </button>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>

        {/* ── CENTER + RIGHT: Results ── */}
        <div className="flex-1 flex flex-col gap-0 overflow-hidden min-w-0">

          {/* Tabs */}
          {(response || aiAnswer) && (
            <div className="flex border-b border-border bg-surface rounded-t-lg">
              {/* PDF Answers tab */}
              <button
                onClick={() => setActiveTab('pdf-answer')}
                className={clsx(
                  "flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors",
                  activeTab === 'pdf-answer'
                    ? "border-primary-accent text-primary-accent font-semibold"
                    : "border-transparent text-secondary-text hover:text-primary-text"
                )}
              >
                <BookOpen size={14} />
                PDF Answers
                {response?.status === 'SUCCESS' && <span className="w-2 h-2 rounded-full bg-green-400 ml-1" />}
              </button>

              {/* AI Answer tab */}
              <button
                onClick={() => setActiveTab('ai-answer')}
                className={clsx(
                  "flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors",
                  activeTab === 'ai-answer'
                    ? isMistralModel ? "border-amber-500 text-amber-600 font-semibold" :
                      isGeminiModel ? "border-blue-500 text-blue-600 font-semibold" :
                      isTavilyModel ? "border-cyan-500 text-cyan-600 font-semibold" :
                      isOpenAlexModel ? "border-violet-500 text-violet-600 font-semibold" :
                      "border-emerald-500 text-emerald-600 font-semibold"
                    : "border-transparent text-secondary-text hover:text-primary-text"
                )}
              >
                {isMistralModel ? <span>🌊</span> : isGeminiModel ? <Sparkles size={14} /> : isTavilyModel ? <Globe size={14} /> : isOpenAlexModel ? <BookMarked size={14} /> : <span className="text-sm">🦙</span>}
                {isMistralModel ? 'Mistral Answer' : isGeminiModel ? 'Gemini Answer' : isTavilyModel ? 'AI Web Answer' : isOpenAlexModel ? 'Academic Literature' : 'Local AI Answer'}
                {isAiLoading && <Loader2 size={11} className="animate-spin ml-1" />}
                {aiAnswer?.status === 'SUCCESS' && !isAiLoading && <span className="w-2 h-2 rounded-full bg-emerald-400 ml-1" />}
              </button>

              {/* Matching Pages tab */}
              <button
                onClick={() => setActiveTab('pages')}
                className={clsx(
                  "flex items-center gap-2 px-5 py-3 text-sm font-medium border-b-2 transition-colors",
                  activeTab === 'pages'
                    ? "border-primary-accent text-primary-accent font-semibold"
                    : "border-transparent text-secondary-text hover:text-primary-text"
                )}
              >
                <List size={14} />
                Matching Pages
                {hasSearchResults && (
                  <span className="bg-primary-accent text-white text-[10px] font-bold px-1.5 py-0.5 rounded-full">
                    {sr!.total_pages}
                  </span>
                )}
              </button>
            </div>
          )}

          <div className="flex-1 overflow-y-auto bg-surface border border-t-0 border-border rounded-b-lg shadow-sm">

            {/* Loading */}
            {isLoading && (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-secondary-text">
                <Loader2 size={32} className="animate-spin text-primary-accent" />
                <div className="text-center">
                  <p className="text-sm font-medium">Searching all pages...</p>
                  <p className="text-xs mt-1 text-gray-400">Retrieving evidence and generating grounded answer</p>
                </div>
              </div>
            )}

            {/* Error */}
            {error && !isLoading && (
              <div className="p-6">
                <div className="p-4 bg-red-50 text-red-600 rounded border border-red-200">
                  <p className="font-medium flex items-center gap-2"><AlertTriangle size={16} /> Error</p>
                  <p className="text-sm mt-1">{error}</p>
                </div>
              </div>
            )}

            {/* Empty state */}
            {!isLoading && !response && !aiAnswer && !error && (
              <div className="flex flex-col items-center justify-center h-full text-secondary-text gap-4">
                <Search size={40} className="text-gray-200" />
                <div className="text-center">
                  <p className="text-sm font-medium text-primary-text">Ready to search</p>
                  <p className="text-xs text-secondary-text mt-1">Enter any term or question to search your document and get AI answers</p>
                </div>
              </div>
            )}

            {/* ── PDF ANSWERS TAB ── */}
            {!isLoading && response && activeTab === 'pdf-answer' && (
              <div className="p-6">
                <div className="flex items-center gap-2 mb-4">
                  <div className="w-8 h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center shadow-sm">
                    <BookOpen size={16} className="text-white" />
                  </div>
                  <div>
                    <h2 className="text-base font-bold text-primary-text">PDF Answers</h2>
                    <p className="text-[10px] text-secondary-text">Grounded strictly in your uploaded document</p>
                  </div>
                </div>

                <div className="mb-4">
                  <h3 className="text-sm font-semibold text-primary-text">{response.search_results?.query || query}</h3>
                </div>

                {response.status === 'ABSTAINED' ? (
                  <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg">
                    <div className="flex items-start gap-2">
                      <AlertCircle size={16} className="text-amber-600 mt-0.5" />
                      <div>
                        <p className="font-medium text-amber-900 text-sm">Insufficient Evidence</p>
                        <p className="text-sm text-amber-800 mt-1">{response.answer}</p>
                      </div>
                    </div>
                    {hasSearchResults && (
                      <button onClick={() => setActiveTab('pages')} className="mt-3 text-xs text-primary-accent hover:underline">
                        View {sr!.total_pages} related pages →
                      </button>
                    )}
                  </div>
                ) : (
                  <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border border-blue-200 rounded-xl p-5 shadow-sm">
                    <p className="text-sm text-primary-text leading-relaxed whitespace-pre-line">{response.answer}</p>
                  </div>
                )}

                {/* Source citations — each P.XX is clickable */}
                {hasEvidence && (
                  <div className="mt-6 pt-4 border-t border-gray-100">
                    <h3 className="text-xs font-bold text-secondary-text uppercase tracking-wider mb-3">
                      Sources ({response.evidence.length} pages) — click to open
                    </h3>
                    <div className="space-y-2">
                      {response.evidence.map((ev, i) => (
                        <div
                          key={i}
                          className="flex items-start gap-3 p-3 bg-gray-50 border border-border rounded-md hover:border-blue-200 hover:bg-blue-50/40 transition-all group cursor-pointer"
                          onClick={() => openPage({ filename: ev.document, page: ev.page })}
                          title={`Open ${ev.document} at page ${ev.page}`}
                        >
                          <div className="flex-shrink-0 flex flex-col items-center gap-1">
                            <PageBadge page={ev.page} document={ev.document} onClick={openPage} />
                            <Eye size={10} className="text-gray-300 group-hover:text-primary-accent transition-colors" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-[10px] font-medium text-secondary-text truncate mb-1">{ev.document}</p>
                            <p className="text-xs text-primary-text leading-relaxed line-clamp-3 italic">
                              "{ev.text.slice(0, 250)}{ev.text.length > 250 ? '...' : ''}"
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {hasSearchResults && (
                  <button
                    onClick={() => setActiveTab('pages')}
                    className="mt-5 text-sm text-primary-accent hover:underline flex items-center gap-1 font-medium"
                  >
                    <List size={14} /> View all {sr!.total_pages} matching pages →
                  </button>
                )}
              </div>
            )}

            {/* ── AI ANSWER TAB ── */}
            {activeTab === 'ai-answer' && (
              <>
                {isAiLoading && (
                  <div className="flex flex-col items-center justify-center h-full gap-4 text-secondary-text">
                    <div className={clsx(
                      "w-12 h-12 rounded-full flex items-center justify-center shadow-lg animate-pulse text-white",
                      isMistralModel ? "bg-gradient-to-br from-amber-500 to-orange-600" :
                      isGeminiModel ? "bg-gradient-to-br from-blue-500 to-indigo-600" :
                      isTavilyModel ? "bg-gradient-to-br from-cyan-500 to-teal-600" :
                      isOpenAlexModel ? "bg-gradient-to-br from-violet-500 to-purple-600" :
                      "bg-gradient-to-br from-emerald-500 to-teal-600"
                    )}>
                      {isMistralModel ? <span className="text-xl">🌊</span> : isGeminiModel ? <Sparkles size={24} /> : isTavilyModel ? <Globe size={24} /> : isOpenAlexModel ? <BookMarked size={24} /> : <span className="text-xl">🦙</span>}
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-medium text-primary-text">
                        {isMistralModel ? `Generating answer with ${activeModelName}...` :
                         isGeminiModel ? `Generating AI answer with ${activeModelName}...` :
                         isTavilyModel ? 'Searching real-time web with Tavily...' :
                         isOpenAlexModel ? 'Searching academic literature on OpenAlex...' :
                         `Generating local AI answer with ${activeModelName}...`}
                      </p>
                      <p className="text-xs mt-1 text-gray-400">
                        {isMistralModel ? 'Mistral AI intelligence engine' :
                         isGeminiModel ? 'Direct general knowledge synthesis' :
                         isTavilyModel ? 'Retrieving live web sources' :
                         isOpenAlexModel ? 'Querying 250M+ research papers' :
                         'Ollama hybrid RAG inference from uploaded PDF'}
                      </p>
                    </div>
                  </div>
                )}
                {!isAiLoading && aiError && (
                  <div className="p-6">
                    <div className="p-4 bg-red-50 text-red-600 rounded border border-red-200">
                      <p className="font-medium flex items-center gap-2"><AlertTriangle size={16} /> Error</p>
                      <p className="text-sm mt-1">{aiError}</p>
                    </div>
                  </div>
                )}
                {!isAiLoading && aiAnswer && <AIAnswerPanel result={aiAnswer} onPageClick={openPage} />}
                {!isAiLoading && !aiAnswer && !aiError && (
                  <div className="flex flex-col items-center justify-center h-full text-secondary-text gap-4">
                    <div className="text-gray-200">
                      {isMistralModel ? <span className="text-5xl">🌊</span> : isGeminiModel ? <Sparkles size={40} /> : isTavilyModel ? <Globe size={40} /> : isOpenAlexModel ? <BookMarked size={40} /> : <span className="text-5xl">🦙</span>}
                    </div>
                    <div className="text-center">
                      <p className="text-sm font-medium text-primary-text">
                        {isMistralModel ? `AI Answer from ${activeModelName}` :
                         isGeminiModel ? `AI Answer from ${activeModelName}` :
                         isTavilyModel ? 'AI Answer from Web Search (Tavily)' :
                         isOpenAlexModel ? 'AI Answer from Academic Literature (OpenAlex)' :
                         `Local AI Answer from ${activeModelName}`}
                      </p>
                      <p className="text-xs text-secondary-text mt-1">
                        {isMistralModel ? 'Run a search to get a Mistral AI-powered direct answer' :
                         isGeminiModel ? 'Run a search to get an AI-powered Gemini direct answer' :
                         isTavilyModel ? 'Run a search to get real-time web search results and summary' :
                         isOpenAlexModel ? 'Run a search to query 250M+ scholarly research papers' :
                         'Ask any question to get an Ollama-powered answer grounded strictly in your uploaded PDF.'}
                      </p>
                    </div>
                  </div>
                )}
              </>
            )}

            {/* ── MATCHING PAGES TAB ── */}
            {!isLoading && response && activeTab === 'pages' && (
              <div className="p-6">
                {hasSearchResults ? (
                  <>
                    <div className="flex items-center justify-between mb-4">
                      <div>
                        <h2 className="text-base font-semibold text-primary-text">
                          "{sr!.query}"
                        </h2>
                        <p className="text-xs text-secondary-text mt-0.5">
                          {sr!.total_pages > 0 ? (
                            <>
                              <strong>{sr!.total_pages} relevant pages</strong>
                              {' · '}
                              {sr!.mode === 'semantic_match'
                                ? <><strong>{sr!.total_matches} semantic passages</strong> · <span className="capitalize font-semibold text-primary-accent">Semantic Retrieval</span></>
                                : <><strong>{sr!.total_matches} exact matches</strong> · <span className="capitalize font-semibold text-primary-accent">{sr!.mode.replace(/_/g, ' ')}</span></>
                              }
                            </>
                          ) : (
                            <span className="font-semibold text-amber-600">No matching pages found</span>
                          )}
                          {' · '}
                          <span className="text-blue-500 flex-inline items-center gap-1">
                            <Eye size={10} className="inline mr-0.5" />Click any P.XX badge to view that page
                          </span>
                        </p>
                      </div>
                    </div>

                    {sr!.results.length > 0 && (
                      <div className="space-y-3 mb-6">
                        {sr!.results.map((result, i) => (
                          <PageResultCard
                            key={`${result.document}-${result.page}-${i}`}
                            result={result}
                            onPageClick={openPage}
                          />
                        ))}
                      </div>
                    )}

                    {/* Related results fallback */}
                    {sr!.results.length === 0 && sr!.related_results && sr!.related_results.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-secondary-text uppercase tracking-wider mb-3">
                          No exact matches — related content:
                        </p>
                        <div className="space-y-3">
                          {sr!.related_results.map((result, i) => (
                            <PageResultCard key={`rel-${result.page}-${i}`} result={result} onPageClick={openPage} />
                          ))}
                        </div>
                      </div>
                    )}

                    {sr!.results.length === 0 && (!sr!.related_results || sr!.related_results.length === 0) && (
                      <div className="text-center py-12 text-secondary-text">
                        <Search size={32} className="mx-auto mb-3 text-gray-300" />
                        <p className="font-medium">No matches found</p>
                        <p className="text-sm mt-1">"{sr!.query}" does not appear in the selected document(s).</p>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="text-center py-12 text-secondary-text">
                    <BookOpen size={32} className="mx-auto mb-3 text-gray-300" />
                    <p className="font-medium">No search results available</p>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
