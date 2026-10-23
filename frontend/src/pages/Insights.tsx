import React, { useState, useEffect } from 'react';
import {
  BarChart2, TrendingUp, Search, FileText,
  AlertCircle, Loader2, RefreshCw, Trash2,
  ChevronRight, Hash, Target, Zap
} from 'lucide-react';
import { useAuth } from '../lib/AuthContext';

interface SearchStats {
  total_searches: number;
  success_rate: number;
  abstention_rate: number;
  avg_result_pages: number;
  top_queries: { query: string; count: number }[];
  searches_per_document: Record<string, number>;
  recent_queries: string[];
  zero_result_queries: string[];
}

interface InsightsData {
  search_stats: SearchStats;
  documents: { filename: string; pages: number; chunks: number; search_count: number }[];
  filtered_by: string | null;
}

function StatCard({ label, value, sub, icon: Icon, color = 'blue' }: {
  label: string; value: string | number; sub?: string;
  icon: React.ElementType; color?: string;
}) {
  const colors: Record<string, string> = {
    blue: 'bg-blue-50 text-blue-600 border-blue-100',
    green: 'bg-green-50 text-green-600 border-green-100',
    amber: 'bg-amber-50 text-amber-600 border-amber-100',
    purple: 'bg-purple-50 text-purple-600 border-purple-100',
  };
  return (
    <div className="bg-white border border-border rounded-xl p-5 shadow-sm">
      <div className="flex items-start justify-between mb-3">
        <span className="text-xs font-semibold text-secondary-text uppercase tracking-wider">{label}</span>
        <div className={`w-8 h-8 rounded-lg border flex items-center justify-center ${colors[color]}`}>
          <Icon size={16} />
        </div>
      </div>
      <p className="text-3xl font-bold text-primary-text">{value}</p>
      {sub && <p className="text-xs text-secondary-text mt-1">{sub}</p>}
    </div>
  );
}

export default function Insights() {
  const { user, getAuthHeaders } = useAuth();
  const [data, setData] = useState<InsightsData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedDoc, setSelectedDoc] = useState<string>('');
  const [clearLoading, setClearLoading] = useState(false);

  const fetchInsights = async (doc?: string) => {
    setIsLoading(true);
    setError(null);
    try {
      const url = doc
        ? `http://localhost:8000/api/v1/history/insights?document=${encodeURIComponent(doc)}`
        : 'http://localhost:8000/api/v1/history/insights';
      const res = await fetch(url, {
        headers: getAuthHeaders()
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setData(await res.json());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setIsLoading(false);
    }
  };

  const clearHistory = async () => {
    if (!confirm(selectedDoc
      ? `Clear search history for "${selectedDoc}"?`
      : 'Clear ALL your search history?')) return;
    setClearLoading(true);
    try {
      const url = selectedDoc
        ? `http://localhost:8000/api/v1/history/search?document=${encodeURIComponent(selectedDoc)}`
        : 'http://localhost:8000/api/v1/history/search';
      await fetch(url, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });
      fetchInsights(selectedDoc || undefined);
    } finally {
      setClearLoading(false);
    }
  };

  useEffect(() => { fetchInsights(); }, [user]);

  const stats = data?.search_stats;

  return (
    <div className="max-w-6xl mx-auto space-y-8">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-primary-text">Search Insights</h1>
          <p className="text-secondary-text text-sm mt-1">
            Personal analytics for <strong className="text-primary-text">{user?.name || user?.email}</strong> — tracking your search activities, queries, and success rate.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => fetchInsights(selectedDoc || undefined)}
            disabled={isLoading}
            className="flex items-center gap-2 px-3 py-2 text-sm border border-border rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50">
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} /> Refresh
          </button>
          <button onClick={clearHistory} disabled={clearLoading}
            className="flex items-center gap-2 px-3 py-2 text-sm border border-red-200 text-red-600 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50">
            <Trash2 size={14} /> Clear My History
          </button>
        </div>
      </div>

      {/* Document filter */}
      {data && data.documents.length > 0 && (
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xs font-medium text-secondary-text">Filter by document:</span>
          <button
            onClick={() => { setSelectedDoc(''); fetchInsights(); }}
            className={`text-xs px-3 py-1.5 rounded-full border transition-colors ${!selectedDoc ? 'bg-primary-accent text-white border-primary-accent' : 'border-border hover:bg-gray-50'}`}
          >
            All Documents
          </button>
          {data.documents.map(doc => (
            <button key={doc.filename}
              onClick={() => { setSelectedDoc(doc.filename); fetchInsights(doc.filename); }}
              className={`text-xs px-3 py-1.5 rounded-full border transition-colors truncate max-w-[200px] ${selectedDoc === doc.filename ? 'bg-primary-accent text-white border-primary-accent' : 'border-border hover:bg-gray-50'}`}
              title={doc.filename}
            >
              {doc.filename}
            </button>
          ))}
        </div>
      )}

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20 text-secondary-text">
          <Loader2 size={28} className="animate-spin text-primary-accent mr-3" />
          <span>Loading insights...</span>
        </div>
      )}

      {/* Error */}
      {error && !isLoading && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm flex items-center gap-2">
          <AlertCircle size={16} /> {error}
        </div>
      )}

      {/* No data yet */}
      {!isLoading && !error && stats && stats.total_searches === 0 && (
        <div className="text-center py-20 text-secondary-text">
          <Search size={48} className="mx-auto mb-4 text-gray-200" />
          <h2 className="text-lg font-semibold text-primary-text mb-2">No searches yet</h2>
          <p className="text-sm">Start searching documents and insights will appear here automatically.</p>
        </div>
      )}

      {/* Stats Grid */}
      {!isLoading && stats && stats.total_searches > 0 && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <StatCard label="Total Searches" value={stats.total_searches} icon={Search} color="blue" sub="All time" />
            <StatCard label="Success Rate" value={`${stats.success_rate}%`} icon={Target} color="green"
              sub="Searches with results" />
            <StatCard label="Avg Pages Found" value={stats.avg_result_pages} icon={FileText} color="purple"
              sub="Per successful search" />
            <StatCard label="No-Result Rate" value={`${stats.abstention_rate}%`} icon={AlertCircle} color="amber"
              sub="Queries with no evidence" />
          </div>

          <div className="grid md:grid-cols-2 gap-6">
            {/* Top Queries */}
            <div className="bg-white border border-border rounded-xl p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <TrendingUp size={18} className="text-primary-accent" />
                <h2 className="text-base font-semibold text-primary-text">Most Searched Terms</h2>
              </div>
              {stats.top_queries.length === 0 ? (
                <p className="text-sm text-secondary-text">No repeated searches yet.</p>
              ) : (
                <div className="space-y-2">
                  {stats.top_queries.map((q, i) => {
                    const maxCount = stats.top_queries[0]?.count || 1;
                    const pct = Math.round((q.count / maxCount) * 100);
                    return (
                      <div key={i}>
                        <div className="flex items-center justify-between mb-1">
                          <span className="text-sm text-primary-text truncate flex-1 mr-2" title={q.query}>
                            <Hash size={11} className="inline text-gray-400 mr-1" />{q.query}
                          </span>
                          <span className="text-xs font-bold text-secondary-text flex-shrink-0">{q.count}×</span>
                        </div>
                        <div className="w-full bg-gray-100 rounded-full h-1.5">
                          <div className="bg-primary-accent h-1.5 rounded-full transition-all duration-500"
                            style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>

            {/* Per-Document Searches */}
            <div className="bg-white border border-border rounded-xl p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <BarChart2 size={18} className="text-primary-accent" />
                <h2 className="text-base font-semibold text-primary-text">Searches per Document</h2>
              </div>
              {Object.keys(stats.searches_per_document).length === 0 ? (
                <p className="text-sm text-secondary-text">No document-specific data yet.</p>
              ) : (
                <div className="space-y-3">
                  {Object.entries(stats.searches_per_document)
                    .sort(([, a], [, b]) => b - a)
                    .map(([doc, count], i) => {
                      const maxCount = Math.max(...Object.values(stats.searches_per_document));
                      const pct = Math.round((count / maxCount) * 100);
                      return (
                        <div key={i}>
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs text-secondary-text truncate flex-1 mr-2" title={doc}>
                              <FileText size={11} className="inline text-gray-400 mr-1" />{doc}
                            </span>
                            <span className="text-xs font-bold">{count}</span>
                          </div>
                          <div className="w-full bg-gray-100 rounded-full h-1.5">
                            <div className="bg-blue-400 h-1.5 rounded-full" style={{ width: `${pct}%` }} />
                          </div>
                        </div>
                      );
                    })}
                </div>
              )}
            </div>

            {/* Recent Searches */}
            <div className="bg-white border border-border rounded-xl p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <Zap size={18} className="text-primary-accent" />
                <h2 className="text-base font-semibold text-primary-text">Recent Searches</h2>
              </div>
              {stats.recent_queries.length === 0 ? (
                <p className="text-sm text-secondary-text">No recent searches.</p>
              ) : (
                <div className="space-y-1">
                  {stats.recent_queries.slice(0, 15).map((q, i) => (
                    <div key={i} className="flex items-center gap-2 py-1.5 border-b border-gray-50 last:border-0">
                      <ChevronRight size={12} className="text-gray-300 flex-shrink-0" />
                      <span className="text-sm text-primary-text truncate">{q}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Zero-result queries */}
            <div className="bg-white border border-border rounded-xl p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <AlertCircle size={18} className="text-amber-500" />
                <h2 className="text-base font-semibold text-primary-text">Unanswered Searches</h2>
                <span className="text-xs text-secondary-text ml-auto">Gaps in your knowledge base</span>
              </div>
              {stats.zero_result_queries.length === 0 ? (
                <div className="flex items-center gap-2 text-green-600 text-sm">
                  <Target size={14} /> All searches returned results — great coverage!
                </div>
              ) : (
                <div className="space-y-1">
                  {stats.zero_result_queries.map((q, i) => (
                    <div key={i} className="flex items-center gap-2 py-1.5 border-b border-gray-50 last:border-0">
                      <span className="w-2 h-2 rounded-full bg-amber-400 flex-shrink-0" />
                      <span className="text-sm text-primary-text truncate">{q}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Documents table */}
          {data && data.documents.length > 0 && (
            <div className="bg-white border border-border rounded-xl p-6 shadow-sm">
              <h2 className="text-base font-semibold text-primary-text mb-4 flex items-center gap-2">
                <FileText size={18} className="text-primary-accent" /> Indexed Documents
              </h2>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left pb-2 font-semibold text-secondary-text text-xs uppercase tracking-wider">Document</th>
                      <th className="text-right pb-2 font-semibold text-secondary-text text-xs uppercase tracking-wider">Pages</th>
                      <th className="text-right pb-2 font-semibold text-secondary-text text-xs uppercase tracking-wider">Chunks</th>
                      <th className="text-right pb-2 font-semibold text-secondary-text text-xs uppercase tracking-wider">Searches</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.documents.map((doc, i) => (
                      <tr key={i} className="border-b border-gray-50 last:border-0">
                        <td className="py-3 pr-4">
                          <div className="flex items-center gap-2">
                            <FileText size={14} className="text-gray-400 flex-shrink-0" />
                            <span className="text-primary-text truncate max-w-xs" title={doc.filename}>{doc.filename}</span>
                          </div>
                        </td>
                        <td className="py-3 text-right text-secondary-text">{doc.pages.toLocaleString()}</td>
                        <td className="py-3 text-right text-secondary-text">{doc.chunks.toLocaleString()}</td>
                        <td className="py-3 text-right">
                          <span className="font-semibold text-primary-accent">{doc.search_count}</span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
