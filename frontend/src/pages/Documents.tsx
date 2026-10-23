import React, { useState, useRef, useEffect } from 'react';
import {
  UploadCloud, File, CheckCircle2, Check, FileText,
  Loader2, Trash2, Search, Eye, ArrowRight, BookOpen, RefreshCw, AlertTriangle
} from 'lucide-react';
import { useApp } from '../lib/AppContext';
import { useAuth } from '../lib/AuthContext';
import { useNavigate } from 'react-router-dom';
import PDFViewerModal from '../components/PDFViewerModal';

interface SelectedFile {
  file: File;
  name: string;
  size: string;
}

interface IndexedDoc {
  filename: string;
  pages: number;
  chunks: number;
  content_type?: string;
}

export default function Documents() {
  const { setDocumentCount, setActiveDocuments } = useApp();
  const { user, getAuthHeaders } = useAuth();
  const navigate = useNavigate();

  // ── Upload flow state ───────────────────────────────────────────────────────
  const [step, setStep] = useState<'idle' | 'processing' | 'done'>('idle');
  const [selectedFiles, setSelectedFiles] = useState<SelectedFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadResults, setUploadResults] = useState<{ filename: string; pages: number }[]>([]);

  // ── Library state ───────────────────────────────────────────────────────────
  const [library, setLibrary] = useState<IndexedDoc[]>([]);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [deletingDoc, setDeletingDoc] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  // ── PDF viewer state ────────────────────────────────────────────────────────
  const [pdfTarget, setPdfTarget] = useState<{ filename: string; page: number } | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Fetch indexed documents ─────────────────────────────────────────────────
  const fetchLibrary = async () => {
    setLibraryLoading(true);
    try {
      const res = await fetch('http://localhost:8000/api/v1/documents/list', {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        const docs: IndexedDoc[] = (data.documents || []).map((d: any) => ({
          filename: d.filename,
          pages: d.pages ?? d.page_count ?? d.indexed_pages ?? 0,
          chunks: d.chunks ?? 0,
          content_type: d.content_type ?? 'application/pdf',
        }));
        setLibrary(docs);
        setDocumentCount(docs.length);
      }
    } catch (e) {
      console.error('Failed to fetch document library:', e);
    } finally {
      setLibraryLoading(false);
    }
  };

  useEffect(() => {
    fetchLibrary();
  }, [user]);

  // ── Delete a document ───────────────────────────────────────────────────────
  const handleDelete = async (filename: string) => {
    setDeletingDoc(filename);
    try {
      await fetch(`http://localhost:8000/api/v1/documents/${encodeURIComponent(filename)}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });
      fetchLibrary();
    } catch (e) {
      console.error('Delete failed:', e);
    } finally {
      setDeletingDoc(null);
      setConfirmDelete(null);
    }
  };

  // ── File validation ─────────────────────────────────────────────────────────
  const formatFileSize = (bytes: number) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  };

  const validateAndAddFiles = (newFiles: File[]) => {
    setUploadError(null);
    const MAX_SIZE = 50 * 1024 * 1024;
    const valid: SelectedFile[] = [];
    for (const file of newFiles) {
      if (!file.name.match(/\.(pdf|docx|txt|csv)$/i)) {
        setUploadError(`Unsupported type: ${file.name}. Please upload PDF, DOCX, TXT or CSV.`);
        continue;
      }
      if (file.size > MAX_SIZE) {
        setUploadError(`File too large (max 50 MB): ${file.name}`);
        continue;
      }
      valid.push({ file, name: file.name, size: formatFileSize(file.size) });
    }
    if (valid.length > 0) setSelectedFiles(prev => [...prev, ...valid]);
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    validateAndAddFiles(Array.from(e.target.files || []));
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    validateAndAddFiles(Array.from(e.dataTransfer.files));
  };

  // ── Upload to backend ───────────────────────────────────────────────────────
  const handleProcessDocuments = async () => {
    setStep('processing');
    setUploadError(null);

    const formData = new FormData();
    selectedFiles.forEach(f => formData.append('files', f.file));
    formData.append('department', 'General');
    formData.append('knowledge_space', 'General Knowledge');
    formData.append('access_level', 'Organization');

    try {
      const res = await fetch('http://localhost:8000/api/v1/documents/upload/', {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData,
      });

      if (!res.ok) throw new Error('Upload failed');

      const data = await res.json();
      // Backend returns { files: [{ filename, pages, ... }] }
      const results = (data.files || data.results || []).map((r: any) => ({
        filename: r.filename,
        pages: r.pages ?? r.page_count ?? 0,
      }));
      setUploadResults(results);
      setStep('done');
      fetchLibrary(); // Refresh library
    } catch (err) {
      console.error(err);
      setUploadError('Upload failed. Make sure the backend server is running on port 8000.');
      setStep('idle');
    }
  };

  const resetUpload = () => {
    setSelectedFiles([]);
    setUploadResults([]);
    setStep('idle');
    setUploadError(null);
  };

  return (
    <>
      {/* PDF Viewer Modal */}
      {pdfTarget && (
        <PDFViewerModal
          filename={pdfTarget.filename}
          initialPage={pdfTarget.page}
          searchQuery=""
          onClose={() => setPdfTarget(null)}
        />
      )}

      {/* Delete Confirmation Modal */}
      {confirmDelete && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-xl p-6 max-w-sm w-full mx-4 border border-border">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 bg-red-50 rounded-full flex items-center justify-center border border-red-200">
                <AlertTriangle size={18} className="text-red-500" />
              </div>
              <div>
                <h3 className="font-semibold text-primary-text text-sm">Delete Document</h3>
                <p className="text-xs text-secondary-text mt-0.5">This cannot be undone</p>
              </div>
            </div>
            <p className="text-sm text-secondary-text mb-5 leading-relaxed">
              Are you sure you want to delete <strong className="text-primary-text truncate">{confirmDelete}</strong>?
              This will remove it from the index and delete the file.
            </p>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setConfirmDelete(null)}
                className="px-4 py-2 text-sm border border-border rounded-md hover:bg-gray-50 transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(confirmDelete)}
                disabled={deletingDoc === confirmDelete}
                className="px-4 py-2 text-sm bg-red-600 text-white rounded-md hover:bg-red-700 transition-colors flex items-center gap-2 disabled:opacity-50"
              >
                {deletingDoc === confirmDelete
                  ? <><Loader2 size={13} className="animate-spin" /> Deleting...</>
                  : <><Trash2 size={13} /> Delete</>}
              </button>
            </div>
          </div>
        </div>
      )}


      <div className="max-w-4xl mx-auto py-8 space-y-10">

        {/* ── Document Library ─────────────────────────────────────────────── */}
        <div>
          <div className="flex items-center justify-between mb-4">
            <div>
              <h1 className="text-2xl font-bold text-primary-text">Documents</h1>
              <p className="text-secondary-text text-sm mt-1">
                Your indexed knowledge base — upload and manage documents here.
              </p>
            </div>
            <button
              onClick={fetchLibrary}
              disabled={libraryLoading}
              className="flex items-center gap-2 px-3 py-2 text-sm border border-border rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-50"
            >
              <RefreshCw size={14} className={libraryLoading ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>

          {libraryLoading ? (
            <div className="flex items-center justify-center py-12 text-secondary-text">
              <Loader2 size={24} className="animate-spin text-primary-accent mr-2" />
              <span className="text-sm">Loading documents...</span>
            </div>
          ) : library.length === 0 ? (
            <div className="text-center py-12 border-2 border-dashed border-border rounded-xl text-secondary-text bg-gray-50">
              <BookOpen size={40} className="mx-auto mb-3 text-gray-300" />
              <p className="text-sm font-medium text-primary-text">No documents indexed yet</p>
              <p className="text-xs mt-1">Upload your first document below to get started.</p>
            </div>
          ) : (
            <div className="border border-border rounded-xl overflow-hidden bg-white shadow-sm">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border bg-gray-50">
                    <th className="text-left px-5 py-3 font-semibold text-secondary-text text-xs uppercase tracking-wider">Document</th>
                    <th className="text-right px-5 py-3 font-semibold text-secondary-text text-xs uppercase tracking-wider">Pages</th>
                    <th className="text-right px-5 py-3 font-semibold text-secondary-text text-xs uppercase tracking-wider">Chunks</th>
                    <th className="text-right px-5 py-3 font-semibold text-secondary-text text-xs uppercase tracking-wider">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {library.map((doc, i) => (
                    <tr key={i} className="border-b border-gray-50 last:border-0 hover:bg-gray-50/60 transition-colors">
                      <td className="px-5 py-4">
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 bg-blue-50 rounded-lg flex items-center justify-center flex-shrink-0">
                            <FileText size={15} className="text-primary-accent" />
                          </div>
                          <div>
                            <p className="font-medium text-primary-text truncate max-w-xs" title={doc.filename}>
                              {doc.filename}
                            </p>
                            <p className="text-xs text-secondary-text mt-0.5">
                              {doc.filename.split('.').pop()?.toUpperCase() ?? 'PDF'}
                            </p>
                          </div>
                        </div>
                      </td>
                      <td className="px-5 py-4 text-right text-secondary-text">
                        {doc.pages.toLocaleString()}
                      </td>
                      <td className="px-5 py-4 text-right text-secondary-text">
                        {doc.chunks.toLocaleString()}
                      </td>
                      <td className="px-5 py-4 text-right">
                      <div className="flex items-center justify-end gap-2">
                          <button
                            onClick={() => setPdfTarget({ filename: doc.filename, page: 1 })}
                            className="flex items-center gap-1.5 text-xs px-3 py-1.5 border border-border rounded-md hover:bg-blue-50 hover:border-blue-200 hover:text-primary-accent transition-colors"
                          >
                            <Eye size={12} /> View
                          </button>
                          <button
                            onClick={() => {
                              setActiveDocuments([doc.filename]);
                              navigate('/analyze');
                            }}
                            className="flex items-center gap-1.5 text-xs px-3 py-1.5 bg-primary-text text-white rounded-md hover:bg-gray-800 transition-colors"
                          >
                            <Search size={12} /> Search
                          </button>
                          <button
                            onClick={() => setConfirmDelete(doc.filename)}
                            disabled={deletingDoc === doc.filename}
                            className="flex items-center justify-center w-7 h-7 text-gray-400 hover:text-red-500 hover:bg-red-50 border border-transparent hover:border-red-200 rounded-md transition-colors disabled:opacity-40"
                            title="Delete document"
                          >
                            {deletingDoc === doc.filename
                              ? <Loader2 size={13} className="animate-spin" />
                              : <Trash2 size={13} />}
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ── Upload Section ────────────────────────────────────────────────── */}
        <div>
          <h2 className="text-lg font-semibold text-primary-text mb-4 flex items-center gap-2">
            <UploadCloud size={20} className="text-primary-accent" />
            Upload New Documents
          </h2>

          {/* Step: Idle — drop zone */}
          {step === 'idle' && (
            <div>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.docx,.txt,.csv"
                onChange={handleFileChange}
                className="hidden"
              />
              <div
                className={`border-2 border-dashed rounded-xl flex flex-col items-center justify-center py-14 transition-colors cursor-pointer group ${
                  isDragging
                    ? 'border-primary-accent bg-blue-50'
                    : 'border-border bg-gray-50 hover:bg-gray-100 hover:border-primary-accent'
                }`}
                onClick={() => fileInputRef.current?.click()}
                onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                onDragLeave={(e) => { e.preventDefault(); setIsDragging(false); }}
                onDrop={handleDrop}
              >
                <div className={`w-14 h-14 bg-white border rounded-full flex items-center justify-center mb-4 transition-colors ${
                  isDragging ? 'border-primary-accent text-primary-accent' : 'border-border text-gray-400 group-hover:border-primary-accent group-hover:text-primary-accent'
                }`}>
                  <UploadCloud size={28} />
                </div>
                <h3 className="text-base font-semibold text-primary-text mb-1">
                  {isDragging ? 'Drop to upload' : 'Drag & drop files here'}
                </h3>
                <p className="text-sm text-secondary-text mb-4">or click to browse</p>
                <div className="flex gap-3 text-xs font-medium text-gray-400 uppercase tracking-wider">
                  <span>PDF</span>•<span>DOCX</span>•<span>TXT</span>•<span>CSV</span>
                </div>
              </div>

              {uploadError && (
                <div className="mt-3 p-3 bg-red-50 text-red-600 border border-red-200 rounded-md text-sm">
                  {uploadError}
                </div>
              )}

              {selectedFiles.length > 0 && (
                <div className="mt-6">
                  <h4 className="text-xs font-semibold text-secondary-text uppercase tracking-wider mb-3">
                    Selected ({selectedFiles.length})
                  </h4>
                  <div className="space-y-2">
                    {selectedFiles.map((f, i) => (
                      <div key={i} className="flex items-center justify-between p-3 bg-white border border-border rounded-lg shadow-sm">
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-blue-50 text-primary-accent rounded">
                            <File size={16} />
                          </div>
                          <div>
                            <p className="text-sm font-medium text-primary-text">{f.name}</p>
                            <p className="text-xs text-secondary-text">{f.size}</p>
                          </div>
                        </div>
                        <button
                          onClick={() => setSelectedFiles(prev => prev.filter((_, j) => j !== i))}
                          className="text-gray-400 hover:text-red-500 transition-colors p-1 rounded"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    ))}
                  </div>
                  <div className="mt-4 flex justify-end">
                    <button
                      onClick={handleProcessDocuments}
                      className="bg-primary-text text-white px-6 py-2.5 rounded-md font-medium hover:bg-gray-800 transition-colors flex items-center gap-2"
                    >
                      <UploadCloud size={16} /> Process Documents
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Step: Processing */}
          {step === 'processing' && (
            <div className="flex flex-col items-center justify-center py-16 text-center border border-border rounded-xl bg-white shadow-sm">
              <Loader2 size={40} className="animate-spin text-primary-accent mb-5" />
              <h2 className="text-xl font-bold text-primary-text mb-1">Processing documents...</h2>
              <p className="text-secondary-text text-sm">
                Extracting pages, indexing content, and building search index.
              </p>
              <div className="mt-6 w-64 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div className="h-full bg-primary-accent rounded-full animate-pulse w-3/4" />
              </div>
            </div>
          )}

          {/* Step: Done */}
          {step === 'done' && (
            <div className="border border-border rounded-xl bg-white shadow-sm overflow-hidden">
              <div className="px-6 py-8 flex flex-col items-center text-center border-b border-border bg-green-50/50">
                <div className="w-14 h-14 bg-green-100 text-green-600 rounded-full flex items-center justify-center mb-4 border border-green-200">
                  <Check size={28} />
                </div>
                <h2 className="text-xl font-bold text-primary-text mb-1">
                  {uploadResults.length === 1 ? 'Document Ready' : `${uploadResults.length} Documents Ready`}
                </h2>
                <p className="text-secondary-text text-sm">
                  {uploadResults.length === 1
                    ? `${uploadResults[0].filename} is now in your knowledge base.`
                    : 'All documents are now in your knowledge base.'}
                </p>
              </div>

              <div className="p-5 space-y-3">
                {uploadResults.map((r, i) => (
                  <div key={i} className="flex items-center justify-between p-3 border border-border rounded-lg">
                    <div className="flex items-center gap-3">
                      <FileText size={16} className="text-gray-400" />
                      <div>
                        <p className="text-sm font-medium text-primary-text">{r.filename}</p>
                        <p className="text-xs text-secondary-text mt-0.5">{r.pages} pages • PDF</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5 text-green-600 text-xs font-medium">
                      <CheckCircle2 size={14} /> Indexed
                    </div>
                  </div>
                ))}
              </div>

              <div className="px-5 py-4 border-t border-border bg-gray-50 flex flex-wrap justify-between items-center gap-3">
                <button
                  onClick={resetUpload}
                  className="text-sm text-secondary-text hover:text-primary-text transition-colors flex items-center gap-1.5"
                >
                  <UploadCloud size={14} /> Upload More
                </button>
                <div className="flex gap-3">
                  <button
                    onClick={() => setPdfTarget({ filename: uploadResults[0].filename, page: 1 })}
                    className="flex items-center gap-2 text-sm border border-border px-4 py-2 rounded-md hover:bg-white transition-colors"
                  >
                    <Eye size={14} /> View Document
                  </button>
                  <button
                    onClick={() => {
                      setActiveDocuments(uploadResults.map(r => r.filename));
                      navigate('/analyze');
                    }}
                    className="flex items-center gap-2 text-sm bg-primary-text text-white px-4 py-2 rounded-md hover:bg-gray-800 transition-colors"
                  >
                    <Search size={14} /> Search This Document
                    <ArrowRight size={14} />
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
