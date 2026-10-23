import React, { useState, useEffect } from 'react';
import {
  AlertTriangle, ShieldAlert, Clock, CheckCircle2,
  XCircle, FileText, Loader2, RefreshCw, AlertCircle,
  Search, Info
} from 'lucide-react';
import clsx from 'clsx';

interface ReviewItem {
  id: number;
  timestamp: string;
  flag_type: string;
  priority: string;
  title: string;
  description: string;
  document_names: string[];
  query: string | null;
  status: string;
}

interface QueueData {
  items: ReviewItem[];
  status_filter: string;
  counts: { pending: number; resolved: number };
}

const PRIORITY_STYLES: Record<string, string> = {
  HIGH:   'bg-red-50 text-red-700 border-red-200',
  MEDIUM: 'bg-amber-50 text-amber-700 border-amber-200',
  LOW:    'bg-blue-50 text-blue-700 border-blue-200',
};

const FLAG_ICONS: Record<string, React.ElementType> = {
  ABSTENTION:     AlertCircle,
  LOW_CONFIDENCE: ShieldAlert,
  PROCESSING:     Clock,
  CONTRADICTION:  AlertTriangle,
};

const FLAG_LABELS: Record<string, string> = {
  ABSTENTION:     'No Evidence Found',
  LOW_CONFIDENCE: 'Low Confidence',
  PROCESSING:     'Processing Issue',
  CONTRADICTION:  'Contradiction',
};

function timeAgo(ts: string): string {
  const diff = Date.now() - new Date(ts).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function ReviewQueue() {
  const [data, setData] = useState<QueueData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'pending' | 'resolved'>('pending');
  const [actionLoading, setActionLoading] = useState<number | null>(null);

  const fetchQueue = async (status = activeTab) => {
    setIsLoading(true);
    try {
      const res = await fetch(`http://localhost:8000/api/v1/history/review-queue?status=${status}`);
      if (res.ok) setData(await res.json());
    } catch (e) {
      console.error(e);
    } finally {
      setIsLoading(false);
    }
  };

  const handleAction = async (id: number, action: 'resolve' | 'dismiss') => {
    setActionLoading(id);
    try {
      await fetch(`http://localhost:8000/api/v1/history/review-queue/${id}?action=${action}`, {
        method: 'PATCH',
      });
      fetchQueue(activeTab);
    } finally {
      setActionLoading(null);
    }
  };

  useEffect(() => { fetchQueue(activeTab); }, [activeTab]);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-bold text-primary-text">Review Queue</h1>
          <p className="text-secondary-text text-sm mt-1">
            Automatically flagged items that may need human attention — abstentions, low-confidence answers, and processing issues.
          </p>
        </div>
        <button onClick={() => fetchQueue(activeTab)} disabled={isLoading}
          className="flex items-center gap-2 px-3 py-2 text-sm border border-border rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50">
          <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} /> Refresh
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 border-b border-border">
        {(['pending', 'resolved'] as const).map(tab => (
          <button key={tab} onClick={() => setActiveTab(tab)}
            className={clsx(
              "flex items-center gap-2 px-5 py-2.5 text-sm font-medium border-b-2 transition-colors capitalize",
              activeTab === tab
                ? "border-primary-accent text-primary-accent"
                : "border-transparent text-secondary-text hover:text-primary-text"
            )}
          >
            {tab === 'pending'
              ? <AlertTriangle size={14} />
              : <CheckCircle2 size={14} />
            }
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
            {data && (
              <span className={clsx(
                "text-[10px] font-bold px-1.5 py-0.5 rounded-full",
                tab === 'pending'
                  ? "bg-red-100 text-red-700"
                  : "bg-green-100 text-green-700"
              )}>
                {tab === 'pending' ? data.counts.pending : data.counts.resolved}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-16 text-secondary-text">
          <Loader2 size={28} className="animate-spin text-primary-accent mr-3" />
          <span>Loading queue...</span>
        </div>
      )}

      {/* Empty */}
      {!isLoading && data && data.items.length === 0 && (
        <div className="text-center py-16 text-secondary-text">
          <CheckCircle2 size={48} className="mx-auto mb-4 text-green-300" />
          <h2 className="text-lg font-semibold text-primary-text mb-2">
            {activeTab === 'pending' ? 'No pending items' : 'No resolved items'}
          </h2>
          <p className="text-sm">
            {activeTab === 'pending'
              ? 'All searches are returning evidence. Items will appear here when the AI abstains or returns low-confidence answers.'
              : 'Resolved items will appear here after you mark pending items as resolved.'}
          </p>
        </div>
      )}

      {/* Items */}
      {!isLoading && data && data.items.length > 0 && (
        <div className="space-y-4">
          {data.items.map(item => {
            const Icon = FLAG_ICONS[item.flag_type] || Info;
            return (
              <div key={item.id}
                className={clsx(
                  "border rounded-xl p-5 bg-white shadow-sm",
                  item.priority === 'HIGH' ? 'border-red-200' :
                  item.priority === 'MEDIUM' ? 'border-amber-200' : 'border-blue-200'
                )}
              >
                <div className="flex items-start gap-4">
                  {/* Priority icon */}
                  <div className={clsx(
                    "w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 border",
                    PRIORITY_STYLES[item.priority] || 'bg-gray-50 text-gray-500 border-gray-200'
                  )}>
                    <Icon size={18} />
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <span className={clsx(
                        "text-[10px] font-bold px-2 py-0.5 rounded border uppercase tracking-wider",
                        PRIORITY_STYLES[item.priority]
                      )}>
                        {item.priority} PRIORITY
                      </span>
                      <span className="text-[10px] font-semibold text-secondary-text bg-gray-100 px-2 py-0.5 rounded uppercase tracking-wider">
                        {FLAG_LABELS[item.flag_type] || item.flag_type}
                      </span>
                      <span className="text-xs text-secondary-text ml-auto">{timeAgo(item.timestamp)}</span>
                    </div>

                    <h3 className="font-semibold text-primary-text text-sm mb-1">{item.title}</h3>
                    <p className="text-xs text-secondary-text leading-relaxed mb-3">{item.description}</p>

                    {/* Meta */}
                    <div className="flex items-center gap-3 flex-wrap text-[11px] text-secondary-text">
                      {item.query && (
                        <span className="flex items-center gap-1">
                          <Search size={10} />
                          Query: <em className="font-medium text-primary-text">"{item.query}"</em>
                        </span>
                      )}
                      {item.document_names && item.document_names.length > 0 && (
                        <span className="flex items-center gap-1">
                          <FileText size={10} />
                          {item.document_names.map(d => (
                            <span key={d} className="bg-gray-100 px-1.5 py-0.5 rounded font-medium text-primary-text">
                              {d}
                            </span>
                          ))}
                        </span>
                      )}
                    </div>

                    {/* Actions (only for pending) */}
                    {item.status === 'pending' && (
                      <div className="flex items-center gap-2 mt-4">
                        <button
                          onClick={() => handleAction(item.id, 'resolve')}
                          disabled={actionLoading === item.id}
                          className="flex items-center gap-1.5 text-xs bg-green-600 text-white px-3 py-1.5 rounded-md hover:bg-green-700 transition-colors disabled:opacity-50"
                        >
                          {actionLoading === item.id
                            ? <Loader2 size={12} className="animate-spin" />
                            : <CheckCircle2 size={12} />
                          }
                          Resolve
                        </button>
                        <button
                          onClick={() => handleAction(item.id, 'dismiss')}
                          disabled={actionLoading === item.id}
                          className="flex items-center gap-1.5 text-xs border border-gray-200 text-secondary-text px-3 py-1.5 rounded-md hover:bg-gray-50 transition-colors disabled:opacity-50"
                        >
                          <XCircle size={12} /> Dismiss
                        </button>
                      </div>
                    )}

                    {item.status === 'resolved' && (
                      <div className="flex items-center gap-1.5 mt-3 text-xs text-green-600">
                        <CheckCircle2 size={12} /> Resolved
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
