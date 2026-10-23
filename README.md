# DocSearch — Project Structure

## Overview
DocSearch is a document intelligence platform with:
- **FastAPI** backend (Python)
- **React + Vite + TypeScript** frontend
- **JSON file storage** for search history, document history, and review queue

---

## Root Layout

```
DocSearch/
├── backend/              # Python FastAPI backend
├── frontend/             # React + TypeScript frontend
├── docker-compose.yml    # Optional Docker setup
├── .env.example          # Environment variable template
└── README.md
```

---

## Backend Structure

```
backend/
├── app/
│   ├── main.py                        # FastAPI app, CORS, router registration
│   │
│   ├── api/
│   │   └── endpoints/
│   │       ├── query.py               # POST /api/v1/query/     → AI search + history recording
│   │       ├── upload.py              # POST /api/v1/documents/upload/  → PDF upload + disk save
│   │       │                          # GET  /api/v1/documents/file/{name} → serve PDF for viewer
│   │       │                          # GET  /api/v1/documents/list        → list all docs
│   │       ├── history.py             # GET  /api/v1/history/search        → search history
│   │       │                          # GET  /api/v1/history/documents      → upload history
│   │       │                          # GET  /api/v1/history/insights       → live analytics
│   │       │                          # GET  /api/v1/history/review-queue   → flagged items
│   │       │                          # PATCH /api/v1/history/review-queue/{id} → resolve/dismiss
│   │       │                          # GET  /api/v1/history/evaluation     → real metrics
│   │       └── compare.py             # POST /api/v1/compare/  → document comparison
│   │
│   ├── services/
│   │   ├── document_store.py          # In-memory + JSON document/chunk store
│   │   ├── search_service.py          # Full-page exhaustive search (no top-K limit)
│   │   ├── retrieval_service.py       # BM25-style evidence retrieval for LLM
│   │   ├── rag_engine.py              # Query classification + orchestration
│   │   ├── llm_service.py             # Google Gemini integration + local fallback
│   │   ├── history_store.py           # ⭐ Search/upload/review history persistence
│   │   └── comparison.py              # Document comparison logic
│   │
│   ├── models/
│   │   └── document.py                # SQLAlchemy models (optional, for future DB)
│   │
│   ├── uploads/                       # ⭐ Saved PDF files (for in-app page viewing)
│   └── data/                          # ⭐ Persistent JSON stores
│       ├── doc_store.json             # Indexed document chunks
│       ├── search_history.json        # Every search query recorded here
│       ├── document_history.json      # Every upload recorded here
│       └── review_queue.json          # Flagged items (abstentions, low confidence)
│
├── requirements.txt
├── .env                               # GEMINI_API_KEY etc.
└── venv/                              # Python virtual environment
```

---

## Frontend Structure

```
frontend/src/
├── App.tsx                            # Router, Sidebar, Topnav layout
├── main.tsx                           # React entry point
│
├── pages/
│   ├── Dashboard.tsx                  # Overview: doc count, quick actions
│   ├── Documents.tsx                  # Upload PDFs, view indexed docs
│   ├── AnalyzeWorkspace.tsx           # ⭐ Main search + AI answer + PDF viewer
│   ├── Compare.tsx                    # Side-by-side document comparison
│   ├── Insights.tsx                   # ⭐ LIVE search analytics from history
│   ├── ReviewQueue.tsx                # ⭐ LIVE flagged items (abstentions etc.)
│   ├── Evaluation.tsx                 # ⭐ LIVE accuracy/performance metrics
│   ├── Settings.tsx                   # LLM status, security policies
│   └── Landing.tsx                    # Marketing/welcome page
│
├── components/
│   └── PDFViewerModal.tsx             # ⭐ In-app PDF viewer with highlighted search terms
│
└── lib/
    └── AppContext.tsx                  # Global state: document count, active docs
```

---

## Key Data Flows

### Search → History → Insights
```
User searches "BPE"
  → POST /api/v1/query/
  → rag_engine.generate_answer()
  → history_store.record_search()  ← saved to search_history.json
  → If ABSTAINED → history_store.add_review_flag()  ← saved to review_queue.json
  → Response returned to frontend

Insights page:
  → GET /api/v1/history/insights
  → history_store.get_search_stats()  ← computed from real data
  → Shows: top queries, success rate, per-document counts
```

### Upload → History
```
User uploads PDF
  → POST /api/v1/documents/upload/
  → Save PDF to backend/app/uploads/  ← enables page viewing
  → Index all pages into doc_store
  → history_store.record_upload()  ← saved to document_history.json
```

### PDF Page Viewing
```
User clicks P.25 badge
  → Opens PDFViewerModal(filename, page=25, searchQuery="BPE")
  → GET /api/v1/documents/file/{filename}  ← serves raw PDF
  → react-pdf renders page 25
  → customTextRenderer highlights "BPE" in yellow
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/query/` | AI search + answer |
| POST | `/api/v1/query/search` | Pure search, all pages |
| POST | `/api/v1/documents/upload/` | Upload + index PDF |
| GET | `/api/v1/documents/file/{name}` | Serve PDF for viewer |
| GET | `/api/v1/documents/list` | List indexed docs |
| GET | `/api/v1/history/search` | Search history |
| GET | `/api/v1/history/documents` | Upload history |
| GET | `/api/v1/history/insights` | Live analytics |
| GET | `/api/v1/history/review-queue` | Flagged items |
| PATCH | `/api/v1/history/review-queue/{id}` | Resolve/dismiss flag |
| GET | `/api/v1/history/evaluation` | Real eval metrics |
| GET | `/api/v1/health/rag` | LLM connection status |

---

## Environment Variables

```env
# backend/.env
GEMINI_API_KEY=your_key_here     # Google Gemini API key (optional - has local fallback)
DATABASE_URL=postgresql://...    # Optional PostgreSQL (not required, JSON is used by default)
```

---

## Running the Project

```bash
# Backend
cd backend
./venv/bin/uvicorn app.main:app --port 8000 --reload

# Frontend (separate terminal)
cd frontend
npm run dev

# Access
Frontend: http://localhost:5173
Backend:  http://localhost:8000
API Docs: http://localhost:8000/docs
```
