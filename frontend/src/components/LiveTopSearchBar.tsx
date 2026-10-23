import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { 
  Search, 
  FileText, 
  ArrowRight, 
  Clock, 
  Sparkles, 
  BookOpen, 
  CornerDownLeft, 
  X, 
  Loader2 
} from 'lucide-react';
import clsx from 'clsx';
import { useApp } from '../lib/AppContext';
import { useAuth } from '../lib/AuthContext';

interface PageResult {
  document: string;
  page: number;
  match_count: number;
  snippets: string[];
}

interface DocResult {
  filename: string;
  pages: number;
  indexed_pages?: number;
}

interface QuickSearchResponse {
  query: string;
  total_matches: number;
  total_pages: number;
  documents: DocResult[];
  pages: PageResult[];
  recent?: any[];
}

export default function LiveTopSearchBar() {
  const [query, setQuery] = useState('');
  const [isOpen, setIsOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [results, setResults] = useState<QuickSearchResponse | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const { setSavedQuery, setActiveDocuments, setSavedActiveTab } = useApp();
  const { getAuthHeaders } = useAuth();
  const navigate = useNavigate();
  const containerRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Global hotkey: Cmd+K or Ctrl+K to focus search bar
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        inputRef.current?.focus();
        setIsOpen(true);
      }
      if (e.key === 'Escape') {
        setIsOpen(false);
        inputRef.current?.blur();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Close on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Live search debounced fetch
  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    const timer = setTimeout(() => {
      fetch(`http://localhost:8000/api/v1/query/quick-search?q=${encodeURIComponent(q)}&limit=5`, {
        headers: getAuthHeaders()
      })
        .then(res => res.json())
        .then((data: QuickSearchResponse) => {
          setResults(data);
          setIsLoading(false);
        })
        .catch(() => {
          setIsLoading(false);
        });
    }, 150);

    return () => clearTimeout(timer);
  }, [query]);

  const handleExecuteSearch = (searchQuery: string, docName?: string, pageNumber?: number) => {
    const targetQ = searchQuery.trim() || query.trim();
    if (!targetQ) return;

    setSavedQuery(targetQ);
    if (docName) {
      setActiveDocuments([docName]);
    }
    setSavedActiveTab(pageNumber ? 'pages' : 'pdf-answer');
    setIsOpen(false);
    navigate('/analyze');
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      handleExecuteSearch(query);
    }
  };

  return (
    <div className="relative w-full max-w-lg" ref={containerRef}>
      <div className="relative">
        <Search className="absolute left-3.5 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setIsOpen(true);
          }}
          onFocus={() => setIsOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search documents, pages, concepts... (⌘K)"
          className="w-full bg-gray-50/80 hover:bg-gray-50 border border-border rounded-lg py-2 pl-10 pr-20 text-xs font-medium text-primary-text focus:outline-none focus:ring-2 focus:ring-primary-accent/20 focus:border-primary-accent focus:bg-white transition-all shadow-sm"
        />
        
        <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center gap-1.5 pointer-events-none">
          {isLoading ? (
            <Loader2 size={13} className="animate-spin text-primary-accent" />
          ) : query ? (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setQuery('');
                setResults(null);
              }}
              className="pointer-events-auto p-0.5 text-gray-400 hover:text-gray-600 rounded"
            >
              <X size={13} />
            </button>
          ) : (
            <kbd className="hidden sm:inline-flex items-center px-1.5 py-0.5 text-[10px] font-mono font-medium text-gray-400 bg-gray-100 border border-border rounded">
              ⌘K
            </kbd>
          )}
        </div>
      </div>

      {/* Floating Live Autocomplete & Results Dropdown */}
      {isOpen && (query.trim() || (results?.recent && results.recent.length > 0)) && (
        <div className="absolute top-full left-0 right-0 mt-2 bg-white border border-border rounded-xl shadow-2xl z-50 overflow-hidden animate-in fade-in zoom-in-95 duration-150 max-h-[480px] flex flex-col">
          
          {/* Header Action / Press Enter */}
          {query.trim() && (
            <div 
              onClick={() => handleExecuteSearch(query)}
              className="p-3 bg-gradient-to-r from-blue-50/70 to-indigo-50/70 border-b border-border flex items-center justify-between cursor-pointer hover:bg-blue-100/50 transition-colors group"
            >
              <div className="flex items-center gap-2.5 text-xs text-primary-accent font-semibold">
                <Sparkles size={14} className="text-primary-accent" />
                <span>Search all documents for "{query}"</span>
              </div>
              <div className="flex items-center gap-1 text-[10px] text-gray-500 group-hover:text-primary-accent font-medium">
                <span>Search</span>
                <CornerDownLeft size={11} />
              </div>
            </div>
          )}

          <div className="overflow-y-auto p-2 space-y-3">
            
            {/* 1. Matched Documents */}
            {results?.documents && results.documents.length > 0 && (
              <div>
                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider px-2.5 py-1">
                  Matching Documents ({results.documents.length})
                </p>
                <div className="space-y-1">
                  {results.documents.map((doc, i) => (
                    <div
                      key={i}
                      onClick={() => handleExecuteSearch(query, doc.filename)}
                      className="flex items-center justify-between p-2 rounded-lg hover:bg-blue-50/60 cursor-pointer transition-colors group"
                    >
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div className="w-6 h-6 rounded bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0">
                          <FileText size={13} />
                        </div>
                        <span className="text-xs font-medium text-primary-text truncate group-hover:text-primary-accent">
                          {doc.filename}
                        </span>
                      </div>
                      <span className="text-[10px] text-gray-400 font-mono flex-shrink-0">
                        {doc.pages} pages
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 2. Live Matching Pages & Snippets */}
            {results?.pages && results.pages.length > 0 && (
              <div>
                <div className="flex items-center justify-between px-2.5 py-1">
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                    Instant Page Matches ({results.total_pages} pages · {results.total_matches} hits)
                  </p>
                </div>
                <div className="space-y-1.5">
                  {results.pages.map((p, i) => (
                    <div
                      key={i}
                      onClick={() => handleExecuteSearch(query, p.document, p.page)}
                      className="p-2.5 rounded-lg border border-transparent hover:border-blue-200 hover:bg-blue-50/40 cursor-pointer transition-all group"
                    >
                      <div className="flex items-center justify-between mb-1">
                        <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-primary-accent bg-blue-100/70 px-2 py-0.5 rounded">
                          <BookOpen size={10} /> Page {p.page}
                        </span>
                        <span className="text-[10px] text-gray-400 truncate max-w-[200px]">
                          {p.document}
                        </span>
                      </div>
                      <p className="text-xs text-gray-600 line-clamp-2 leading-relaxed italic">
                        "{p.snippets[0]?.replace(/\*\*/g, '') || 'Matching page content'}"
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* 3. Empty State */}
            {query.trim() && !isLoading && results && results.pages.length === 0 && results.documents.length === 0 && (
              <div className="py-6 text-center text-gray-400">
                <Search size={24} className="mx-auto text-gray-300 mb-2" />
                <p className="text-xs font-medium text-gray-600">No exact page hits found for "{query}"</p>
                <p className="text-[11px] text-gray-400 mt-1">Press Enter to run full conceptual AI search</p>
              </div>
            )}
          </div>

          {/* Footer Navigation Tip */}
          <div className="p-2 bg-gray-50 border-t border-border flex items-center justify-between text-[10px] text-gray-400 px-3">
            <span className="flex items-center gap-1">
              <span className="font-semibold text-gray-600">Esc</span> to dismiss
            </span>
            <span className="text-primary-accent font-medium hover:underline cursor-pointer" onClick={() => handleExecuteSearch(query)}>
              Open Full Search Workspace →
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
