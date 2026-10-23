import React, { useState, useEffect } from 'react';
import { FileText, Layers, Search, ShieldCheck, Clock, FileUp, AlertCircle, Database, CheckCircle2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import clsx from 'clsx';
import { useApp } from '../lib/AppContext';
import { useAuth } from '../lib/AuthContext';

export default function Dashboard() {
  const { appState, documentCount } = useApp();
  const { user, getAuthHeaders } = useAuth();
  const navigate = useNavigate();

  const [metrics, setMetrics] = useState({
    documents: '0',
    indexed_pages: '0',
    queries_today: '0',
    verified_percentage: '100%'
  });

  useEffect(() => {
    fetch('http://localhost:8000/api/v1/analytics/dashboard', {
      headers: getAuthHeaders()
    })
      .then(res => res.json())
      .then(data => {
        setMetrics({
          documents: (data.documents ?? documentCount).toLocaleString(),
          indexed_pages: (data.indexed_pages ?? 0).toLocaleString(),
          queries_today: (data.queries_today ?? 0).toLocaleString(),
          verified_percentage: (data.verified_percentage ?? 100) + '%'
        });
      })
      .catch(err => console.error("Failed to fetch dashboard metrics", err));
  }, [appState, documentCount, user]);

  if (documentCount === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-12rem)] max-w-2xl mx-auto text-center">
        <div className="w-16 h-16 bg-blue-50 border border-blue-100 text-primary-accent rounded-xl flex items-center justify-center mb-6">
          <Database size={32} />
        </div>
        <h1 className="text-3xl font-bold text-primary-text mb-3">Build your knowledge base</h1>
        <p className="text-secondary-text mb-8 max-w-lg text-lg">
          Welcome <span className="font-semibold text-primary-text">{user?.name || user?.email}</span>! Your document workspace is currently empty. Upload your documents to begin searching and analyzing them.
        </p>
        
        <div className="flex items-center gap-4">
          <button 
            onClick={() => navigate('/documents')}
            className="bg-primary-text text-white px-6 py-3 rounded-md font-medium hover:bg-gray-800 transition-colors shadow-sm flex items-center gap-2"
          >
            <FileUp size={18} /> Upload your first document
          </button>
        </div>

        <div className="mt-16 flex items-center justify-center gap-4 text-xs font-bold uppercase tracking-wider text-secondary-text">
          <div className="flex flex-col items-center gap-2"><div className="w-8 h-8 rounded-full border-2 border-gray-200 flex items-center justify-center">1</div> UPLOAD</div>
          <div className="w-8 h-px bg-gray-200"></div>
          <div className="flex flex-col items-center gap-2 opacity-50"><div className="w-8 h-8 rounded-full border-2 border-gray-200 flex items-center justify-center">2</div> PROCESS</div>
          <div className="w-8 h-px bg-gray-200"></div>
          <div className="flex flex-col items-center gap-2 opacity-50"><div className="w-8 h-8 rounded-full border-2 border-gray-200 flex items-center justify-center">3</div> INDEX</div>
          <div className="w-8 h-px bg-gray-200"></div>
          <div className="flex flex-col items-center gap-2 opacity-50"><div className="w-8 h-8 rounded-full border-2 border-gray-200 flex items-center justify-center">4</div> ANALYZE</div>
        </div>
      </div>
    );
  }

  if (appState === 'processing') {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-12rem)] max-w-md mx-auto text-center">
        <div className="w-16 h-16 border-4 border-gray-200 border-t-primary-accent rounded-full animate-spin mb-6"></div>
        <h1 className="text-2xl font-bold text-primary-text mb-2">Your documents are being indexed</h1>
        <p className="text-secondary-text mb-8">
          DocSearch is extracting and indexing information from your uploaded documents.
        </p>
        <button 
          onClick={() => navigate('/documents')}
          className="text-primary-accent hover:underline font-medium"
        >
          View Processing Status
        </button>
      </div>
    );
  }

  if (appState === 'ready') {
    return (
      <div className="flex flex-col items-center justify-center h-[calc(100vh-12rem)] max-w-2xl mx-auto text-center animate-in fade-in zoom-in-95 duration-500">
        <div className="w-20 h-20 bg-green-50 text-success rounded-full flex items-center justify-center mb-6 border border-green-100">
          <CheckCircle2 size={40} />
        </div>
        <h1 className="text-3xl font-bold text-primary-text mb-2">Your knowledge base is ready.</h1>
        <p className="text-secondary-text mb-8 text-lg">
          {documentCount} document{documentCount !== 1 ? 's' : ''} successfully indexed and ready for analysis.
        </p>
        
        <div className="flex items-center gap-4">
          <button 
            onClick={() => navigate('/analyze')}
            className="bg-primary-text text-white px-8 py-3 rounded-md font-medium hover:bg-gray-800 transition-colors shadow-sm flex items-center gap-2"
          >
            <Search size={18} /> Search &amp; Analyze
          </button>
          <button 
            onClick={() => navigate('/documents')}
            className="bg-white border border-border text-primary-text px-8 py-3 rounded-md font-medium hover:bg-gray-50 transition-colors"
          >
            Upload more documents
          </button>
        </div>
      </div>
    );
  }

  // ACTIVE ORGANIZATION STATE (Existing Dashboard)
  const stats = [
    { label: 'Total Documents', value: metrics.documents, icon: FileText, trend: '+12 this week' },
    { label: 'Indexed Pages', value: metrics.indexed_pages, icon: Layers, trend: '+340 this week' },
    { label: 'Knowledge Queries', value: metrics.queries_today, icon: Search, trend: '+89 today' },
    { label: 'Verified Answers', value: metrics.verified_percentage, icon: ShieldCheck, trend: '+0.2% vs last month' },
  ];

  return (
    <div className="flex flex-col gap-8 max-w-6xl mx-auto w-full pb-10">
      <div>
        <h1 className="text-2xl font-bold text-primary-text mb-1">
          Good morning, {user?.name || user?.email?.split('@')[0] || 'User'}
        </h1>
        <p className="text-secondary-text">Your Knowledge Base Overview</p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, i) => (
          <div key={i} className="bg-surface border border-border rounded-lg p-5 shadow-sm hover:shadow-md transition-shadow">
            <div className="flex justify-between items-start mb-4">
              <div className="p-2 bg-blue-50 text-primary-accent rounded-md">
                <stat.icon size={20} />
              </div>
            </div>
            <h3 className="text-3xl font-bold text-primary-text mb-1">{stat.value}</h3>
            <p className="text-sm font-medium text-secondary-text">{stat.label}</p>
            <p className="text-xs text-secondary-text mt-3 pt-3 border-t border-gray-100">{stat.trend}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-surface border border-border rounded-lg shadow-sm">
          <div className="px-6 py-4 border-b border-border flex justify-between items-center">
            <h2 className="text-lg font-semibold text-primary-text">Document Activity</h2>
            <button className="text-sm text-primary-accent hover:underline font-medium">View all</button>
          </div>
          <div className="p-0">
            <table className="w-full text-sm text-left">
              <thead className="text-xs text-secondary-text uppercase bg-gray-50 border-b border-border">
                <tr>
                  <th className="px-6 py-3 font-medium">Document Name</th>
                  <th className="px-6 py-3 font-medium">Department</th>
                  <th className="px-6 py-3 font-medium">Status</th>
                  <th className="px-6 py-3 font-medium">Last Updated</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {[
                  { name: 'Employee_Handbook_2026.pdf', dept: 'HR', status: 'Indexed', date: 'Oct 02, 2026', sColor: 'bg-green-100 text-green-800' },
                  { name: 'Q3_Financial_Report.docx', dept: 'Finance', status: 'Processing', date: 'Oct 03, 2026', sColor: 'bg-amber-100 text-amber-800' },
                  { name: 'Compliance_Guidelines_v3.pdf', dept: 'Legal', status: 'Needs Review', date: 'Oct 01, 2026', sColor: 'bg-red-100 text-red-800' },
                  { name: 'Remote_Work_Policy.pdf', dept: 'Operations', status: 'Indexed', date: 'Sep 28, 2026', sColor: 'bg-green-100 text-green-800' },
                ].map((doc, i) => (
                  <tr key={i} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 font-medium text-primary-text flex items-center gap-2">
                      <FileText size={16} className="text-gray-400" />
                      {doc.name}
                    </td>
                    <td className="px-6 py-4 text-secondary-text">{doc.dept}</td>
                    <td className="px-6 py-4">
                      <span className={clsx("px-2.5 py-0.5 rounded-full text-xs font-medium", doc.sColor)}>
                        {doc.status}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-secondary-text">{doc.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-surface border border-border rounded-lg shadow-sm flex flex-col">
          <div className="px-6 py-4 border-b border-border">
            <h2 className="text-lg font-semibold text-primary-text">Pending Reviews</h2>
          </div>
          <div className="p-4 flex-1 flex flex-col gap-3">
            {[
              { title: 'Potential conflict detected', doc: 'Leave_Policy_2026.pdf', type: 'Contradiction', icon: AlertCircle, color: 'text-amber-500' },
              { title: 'Unsupported claim in response', query: '"What is the max expenses?"', type: 'Verification', icon: ShieldCheck, color: 'text-red-500' },
              { title: 'Document processing failed', doc: 'Scanned_Receipts_Oct.pdf', type: 'OCR Engine', icon: Clock, color: 'text-gray-500' },
            ].map((review, i) => (
              <div key={i} className="p-3 border border-border rounded-md hover:border-gray-300 transition-colors cursor-pointer group">
                <div className="flex gap-3">
                  <review.icon size={18} className={clsx("mt-0.5", review.color)} />
                  <div>
                    <p className="text-sm font-medium text-primary-text group-hover:text-primary-accent transition-colors">{review.title}</p>
                    <p className="text-xs text-secondary-text mt-1">{review.doc || review.query}</p>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-[10px] uppercase tracking-wider font-semibold text-gray-500 bg-gray-100 px-2 py-0.5 rounded">
                        {review.type}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
            <button onClick={() => navigate('/review')} className="mt-auto w-full py-2 text-sm font-medium text-primary-accent border border-primary-accent/20 rounded-md hover:bg-blue-50 transition-colors">
              Go to Review Queue
            </button>
          </div>
        </div>
      </div>
      
      <div className="bg-surface border border-border rounded-lg shadow-sm p-6">
        <h2 className="text-lg font-semibold text-primary-text mb-4">Evidence Quality Metrics</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <div>
            <p className="text-sm text-secondary-text mb-1">Citation Validity</p>
            <div className="flex items-end gap-2">
              <span className="text-2xl font-bold text-success">98.2%</span>
              <span className="text-xs text-secondary-text mb-1 pb-0.5">verified</span>
            </div>
          </div>
          <div>
            <p className="text-sm text-secondary-text mb-1">Retrieval Success</p>
            <div className="flex items-end gap-2">
              <span className="text-2xl font-bold text-primary-text">96.5%</span>
              <span className="text-xs text-secondary-text mb-1 pb-0.5">Top-5 chunks</span>
            </div>
          </div>
          <div>
            <p className="text-sm text-secondary-text mb-1">Unsupported Claim Rate</p>
            <div className="flex items-end gap-2">
              <span className="text-2xl font-bold text-success">1.3%</span>
              <span className="text-xs text-secondary-text mb-1 pb-0.5">requires review</span>
            </div>
          </div>
          <div>
            <p className="text-sm text-secondary-text mb-1">Avg Response Latency</p>
            <div className="flex items-end gap-2">
              <span className="text-2xl font-bold text-primary-text">1.2s</span>
              <span className="text-xs text-secondary-text mb-1 pb-0.5">end-to-end</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
