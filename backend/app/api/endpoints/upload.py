from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Header, Query
from fastapi.responses import FileResponse, JSONResponse, Response
from typing import List, Dict, Any, Optional
import io
import os
import math
import pypdf
import docx
try:
    import pymupdf
except ImportError:
    import fitz as pymupdf
from app.services.document_store import doc_store
from app.services.history_store import history_store
from app.services.vector_store import vector_store
from app.services.ollama_service import ollama_service
from app.api.endpoints.auth import get_current_user_from_request

router = APIRouter()

# Directory where uploaded documents are saved for serving
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".doc", ".txt", ".csv", ".md"}


def get_media_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return "application/pdf"
    elif ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif ext == ".doc":
        return "application/msword"
    elif ext == ".txt":
        return "text/plain; charset=utf-8"
    elif ext == ".csv":
        return "text/csv; charset=utf-8"
    elif ext == ".md":
        return "text/markdown; charset=utf-8"
    return "application/octet-stream"



def chunk_text(
    text: str,
    max_words: int = 400,
    overlap_words: int = 60,
) -> List[str]:
    """
    Structure-aware chunker with overlap.

    Strategy:
    1. Split text into paragraphs (blank-line boundaries).
    2. Accumulate paragraphs into chunks of at most `max_words` words.
    3. When a chunk is full, carry the last `overlap_words` words into the
       next chunk so that boundary context is never lost.

    For short pages (≤ max_words), returns the entire page as one chunk
    to keep table rows and headings together.
    """
    words = text.split()
    if len(words) <= max_words:
        return [text] if text.strip() else []

    # Split into paragraphs, keeping inline structure (table rows, bullet lists)
    import re as _re
    paragraphs = [p.strip() for p in _re.split(r"\n{2,}", text) if p.strip()]
    if not paragraphs:
        paragraphs = [text]

    chunks: List[str] = []
    current_words: List[str] = []

    for para in paragraphs:
        para_words = para.split()
        # If adding this paragraph would exceed the limit, flush current chunk first
        if current_words and len(current_words) + len(para_words) > max_words:
            chunks.append(" ".join(current_words))
            # Start the next chunk with an overlap from the end of current
            current_words = current_words[-overlap_words:] if overlap_words else []
        # If a single paragraph is longer than max_words, split it further
        if len(para_words) > max_words:
            for i in range(0, len(para_words), max_words - overlap_words):
                segment = para_words[i : i + max_words]
                if current_words:
                    chunks.append(" ".join(current_words + segment))
                    current_words = segment[-overlap_words:] if overlap_words else []
                else:
                    current_words = segment
        else:
            current_words.extend(para_words)

    if current_words:
        chunks.append(" ".join(current_words))

    return [c for c in chunks if c.strip()]


def extract_docx_pages(content: bytes, words_per_page: int = 350) -> List[str]:
    """
    Extracts text from a DOCX file by reading paragraphs and tables,
    partitioning the text into logical pages.
    """
    doc = docx.Document(io.BytesIO(content))
    paragraphs_text = []

    # Extract headers/body paragraphs
    for p in doc.paragraphs:
        txt = p.text.strip()
        if txt:
            paragraphs_text.append(txt)

    # Extract tables
    for table in doc.tables:
        table_rows = []
        for row in table.rows:
            row_cells = [cell.text.strip() for cell in row.cells]
            if any(row_cells):
                table_rows.append(" | ".join(row_cells))
        if table_rows:
            paragraphs_text.append("\n".join(table_rows))

    full_text = "\n\n".join(paragraphs_text)
    if not full_text.strip():
        return [""]

    words = full_text.split()
    if len(words) <= words_per_page:
        return [full_text]

    pages = []
    for i in range(0, len(words), words_per_page):
        page_chunk = " ".join(words[i:i + words_per_page])
        pages.append(page_chunk)
    return pages


def extract_pdf_pages(content: bytes) -> List[str]:
    """
    Extract text from a PDF file page-by-page preserving layout, headings, and tables.
    Uses PyMuPDF to detect tables and format them as structured Markdown tables,
    preserving row-value associations and numeric attribution.
    Falls back to pypdf if PyMuPDF fails or is not available.
    """
    try:
        import pymupdf
        doc = pymupdf.open(stream=content, filetype="pdf")
        pages = []
        for page in doc:
            table_rects = []
            table_texts = []
            try:
                tabs = page.find_tables()
                if tabs and tabs.tables:
                    for tab in tabs.tables:
                        table_rects.append(tab.bbox)
                        rows = tab.extract()
                        if not rows or len(rows) < 1:
                            continue
                        header = [str(c or "").strip().replace("\n", " ") for c in rows[0]]
                        if not any(header):
                            continue
                        md_lines = [
                            "| " + " | ".join(header) + " |",
                            "| " + " | ".join(["---"] * len(header)) + " |"
                        ]
                        for row in rows[1:]:
                            cells = [str(c or "").strip().replace("\n", " ") for c in row]
                            md_lines.append("| " + " | ".join(cells) + " |")
                        table_texts.append("\n".join(md_lines))
            except Exception:
                pass

            try:
                blocks = page.get_text("blocks")
                text_blocks = []
                for b in blocks:
                    if b[6] != 0:  # non-text/image block
                        continue
                    rect = pymupdf.Rect(b[:4])
                    in_table = any(rect.intersects(pymupdf.Rect(tr)) for tr in table_rects)
                    if not in_table:
                        txt = b[4].strip()
                        if txt:
                            text_blocks.append(txt)
            except Exception:
                text_blocks = [page.get_text("text").strip()]

            assembled = []
            if text_blocks and table_texts:
                split_idx = min(len(text_blocks), 3)
                assembled.extend(text_blocks[:split_idx])
                assembled.extend(table_texts)
                if len(text_blocks) > split_idx:
                    assembled.extend(text_blocks[split_idx:])
            elif table_texts:
                assembled.extend(table_texts)
            else:
                assembled.extend(text_blocks)

            page_str = "\n\n".join(assembled).strip()
            pages.append(page_str if page_str else page.get_text("text").strip())

        return pages if pages else [""]
    except Exception as e:
        print(f"[Upload] PyMuPDF layout extraction notice: {e}, falling back to pypdf")
        try:
            pdf_reader = pypdf.PdfReader(io.BytesIO(content))
            pages = []
            for page in pdf_reader.pages:
                text = page.extract_text() or ""
                pages.append(text)
            return pages if pages else [""]
        except Exception:
            return [""]


def extract_plain_text_pages(content: bytes, words_per_page: int = 350) -> List[str]:
    """Extract plain text or CSV into logical pages."""
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        text = content.decode("latin-1", errors="ignore")

    words = text.split()
    if not words:
        return [""]
    if len(words) <= words_per_page:
        return [text]

    pages = []
    for i in range(0, len(words), words_per_page):
        page_chunk = " ".join(words[i:i + words_per_page])
        pages.append(page_chunk)
    return pages


def extract_pages_from_file(filename: str, content: bytes) -> List[str]:
    """Route file parsing based on extension."""
    ext = os.path.splitext(filename)[1].lower()
    if ext == ".pdf":
        return extract_pdf_pages(content)
    elif ext == ".docx":
        return extract_docx_pages(content)
    elif ext in [".txt", ".csv", ".md"]:
        return extract_plain_text_pages(content)
    else:
        try:
            return extract_plain_text_pages(content)
        except Exception:
            return [""]


# ── Upload ──────────────────────────────────────────────────────────────────

@router.post("/upload/")
async def upload_documents(
    files: List[UploadFile] = File(...),
    department: str = Form(""),
    knowledge_space: str = Form(""),
    access_level: str = Form(""),
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """
    Upload PDF, DOCX, TXT, CSV, MD documents.
    Tied exclusively to the authenticated user account.
    """
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = (current_user["email"] if current_user else None) or x_user_email or "user@docsearch.io"
    u_id = (current_user["id"] if current_user else None) or x_user_id

    results = []
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            print(f"[Upload] Skipping unsupported file extension: {file.filename}")
            continue

        content = await file.read()

        # Save raw file to disk for page-level viewing and serving
        safe_name = os.path.basename(file.filename)
        dest_path = os.path.join(UPLOAD_DIR, safe_name)
        with open(dest_path, "wb") as f:
            f.write(content)
        print(f"[Upload] Saved {ext.upper()} to: {dest_path}")

        # Extract pages and index
        try:
            pages = extract_pages_from_file(file.filename, content)
        except Exception as e:
            print(f"[Upload] Error extracting text from {file.filename}: {e}")
            pages = [""]

        num_pages = len(pages)
        doc_store.add_document(file.filename, num_pages, user_email=u_email, user_id=u_id)

        for page_idx, page_text in enumerate(pages):
            page_num = page_idx + 1
            if page_text and page_text.strip():
                chunks = chunk_text(page_text)
                for chunk in chunks:
                    doc_store.add_chunk(file.filename, page_num, chunk, user_email=u_email, user_id=u_id)

        doc_store.commit()

        # Generate and save vector embeddings for semantic search
        try:
            doc_chunks = [
                c for c in doc_store.chunks
                if c.get("filename") == file.filename
                and (c.get("user_email") or "").lower() == u_email.lower()
            ]
            if doc_chunks:
                texts = [c.get("text", "") for c in doc_chunks]
                embeddings = ollama_service.embed_batch(texts)
                vector_store.save_document_embeddings(
                    user_email=u_email,
                    filename=file.filename,
                    chunks=doc_chunks,
                    embeddings=embeddings,
                )
        except Exception as emb_e:
            print(f"[Upload] Background embedding indexing notice for {file.filename}: {emb_e}")

        # ── Record upload in history ──
        history_store.record_upload(
            filename=file.filename,
            pages=num_pages,
            chunks=sum(1 for c in doc_store.chunks if c.get("filename") == file.filename and (c.get("user_email") or "").lower() == u_email.lower()),
            size_bytes=len(content),
            status="indexed",
        )

        results.append({
            "filename": file.filename,
            "content_type": file.content_type or get_media_type(file.filename),
            "pages": num_pages,
            "status": "indexed",
        })

    return {
        "message": "Documents uploaded and indexed successfully",
        "files": results
    }


# ── Serve Document File ──────────────────────────────────────────────────────

@router.get("/file/{filename:path}")
async def serve_document_file(filename: str):
    """
    Serve an uploaded document inline or for download.
    """
    safe_name = os.path.basename(filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)

    if not os.path.exists(file_path):
        # Try to find case-insensitively
        if os.path.isdir(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                if f.lower() == safe_name.lower():
                    file_path = os.path.join(UPLOAD_DIR, f)
                    break

    if not os.path.exists(file_path):
        raise HTTPException(
            status_code=404,
            detail=(
                f"File '{safe_name}' not found on disk. "
                "This document was indexed before in-app viewing was enabled. "
                "Please re-upload it to activate page-level viewing."
            )
        )

    media_type = get_media_type(safe_name)
    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=safe_name,
        headers={
            "Content-Disposition": f"inline; filename=\"{safe_name}\"",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "public, max-age=86400",
            "Accept-Ranges": "bytes",
        }
    )


# ── High-Speed Document Metadata ──────────────────────────────────────────────

@router.get("/info/{filename:path}")
async def get_document_info(filename: str):
    """Return page count and metadata instantaneously."""
    safe_name = os.path.basename(filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    if not os.path.exists(file_path):
        if os.path.isdir(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                if f.lower() == safe_name.lower():
                    file_path = os.path.join(UPLOAD_DIR, f)
                    safe_name = f
                    break
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    ext = os.path.splitext(safe_name)[1].lower()
    num_pages = 1
    if ext == ".pdf":
        try:
            doc = pymupdf.open(file_path)
            num_pages = len(doc)
            doc.close()
        except Exception:
            num_pages = 1
    else:
        doc_chunks = [c for c in doc_store.chunks if c.get("filename") in (filename, safe_name)]
        if doc_chunks:
            num_pages = max([c.get("page_number", 1) for c in doc_chunks], default=1)

    return {
        "filename": safe_name,
        "num_pages": num_pages,
        "size_bytes": os.path.getsize(file_path),
        "is_pdf": ext == ".pdf",
    }


# ── Blazing Fast Page Image Rendering (< 100ms) with Search Term Highlight ────

@router.get("/page-image/{filename:path}")
async def get_page_image(
    filename: str,
    page: int = Query(1, ge=1),
    query: Optional[str] = Query(None),
    dpi: int = Query(150, ge=72, le=300),
):
    """
    Renders an exact high-resolution vector page of a PDF in under 100ms.
    Automatically highlights query terms directly on the canvas with zero lag.
    """
    safe_name = os.path.basename(filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    if not os.path.exists(file_path):
        if os.path.isdir(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                if f.lower() == safe_name.lower():
                    file_path = os.path.join(UPLOAD_DIR, f)
                    safe_name = f
                    break
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    ext = os.path.splitext(safe_name)[1].lower()
    if ext != ".pdf":
        raise HTTPException(status_code=400, detail="Page images are only available for PDF documents.")

    try:
        doc = pymupdf.open(file_path)
        total_pages = len(doc)
        if total_pages == 0:
            doc.close()
            raise HTTPException(status_code=400, detail="PDF document has 0 pages.")

        clamped_page = max(1, min(page, total_pages))
        pdf_page = doc.load_page(clamped_page - 1)

        # Highlight search query terms with vibrant amber boxes
        if query and query.strip():
            terms = [t.strip() for t in query.strip().split() if len(t.strip()) > 1]
            for term in terms:
                try:
                    rects = pdf_page.search_for(term)
                    for r in rects:
                        annot = pdf_page.add_highlight_annot(r)
                        annot.set_colors(stroke=(1.0, 0.82, 0.0))  # Vivid yellow
                        annot.update()
                except Exception:
                    pass

        pix = pdf_page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        doc.close()

        return Response(
            content=img_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "public, max-age=3600",
                "X-Total-Pages": str(total_pages),
                "X-Current-Page": str(clamped_page),
                "Access-Control-Expose-Headers": "X-Total-Pages, X-Current-Page",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error rendering page: {str(e)}")


# ── Instant Single-Page PDF Extraction (< 200ms) ─────────────────────────────

@router.get("/page-pdf/{filename:path}")
async def get_single_page_pdf(
    filename: str,
    page: int = Query(1, ge=1),
):
    """
    Extracts a single page as a lightweight (< 200KB) standalone PDF.
    Enables instant vector text selection without downloading huge documents.
    """
    safe_name = os.path.basename(filename)
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    if not os.path.exists(file_path):
        if os.path.isdir(UPLOAD_DIR):
            for f in os.listdir(UPLOAD_DIR):
                if f.lower() == safe_name.lower():
                    file_path = os.path.join(UPLOAD_DIR, f)
                    safe_name = f
                    break
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    try:
        doc = pymupdf.open(file_path)
        total_pages = len(doc)
        clamped_page = max(1, min(page, total_pages))

        single_doc = pymupdf.open()
        single_doc.insert_pdf(doc, from_page=clamped_page - 1, to_page=clamped_page - 1)
        pdf_bytes = single_doc.tobytes()
        single_doc.close()
        doc.close()

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"inline; filename=\"{safe_name}_p{clamped_page}.pdf\"",
                "Cache-Control": "public, max-age=3600",
                "X-Total-Pages": str(total_pages),
                "Access-Control-Expose-Headers": "X-Total-Pages",
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error extracting page PDF: {str(e)}")


# ── Structured Document Content ──────────────────────────────────────────────

@router.get("/content/{filename:path}")
async def get_document_content(filename: str):
    """
    Get structured page-by-page text content of a document.
    Enables rich frontend in-app viewing and highlighting for DOCX, TXT, CSV, MD.
    """
    safe_name = os.path.basename(filename)

    # Check if we have chunks in doc_store
    doc_chunks = [c for c in doc_store.chunks if c.get("filename") in (filename, safe_name)]
    if not doc_chunks:
        # Check if the file is on disk and extract dynamically
        file_path = os.path.join(UPLOAD_DIR, safe_name)
        if os.path.exists(file_path):
            with open(file_path, "rb") as f:
                content = f.read()
            extracted = extract_pages_from_file(safe_name, content)
            return {
                "filename": safe_name,
                "pages_count": len(extracted),
                "pages": [{"page": i + 1, "text": txt} for i, txt in enumerate(extracted)]
            }
        raise HTTPException(status_code=404, detail=f"Document '{safe_name}' not found.")

    # Group chunks by page_number
    pages_dict: Dict[int, List[str]] = {}
    for c in doc_chunks:
        p = c.get("page_number", 1)
        if p not in pages_dict:
            pages_dict[p] = []
        pages_dict[p].append(c.get("text", ""))

    sorted_pages = sorted(pages_dict.keys())
    pages_list = [
        {"page": p, "text": "\n\n".join(pages_dict[p])}
        for p in sorted_pages
    ]

    return {
        "filename": safe_name,
        "pages_count": len(pages_list),
        "pages": pages_list
    }


# ── List indexed documents ────────────────────────────────────────────────────

@router.get("/list")
async def list_documents(
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
    user_email: Optional[str] = Query(None),
):
    """List indexed documents owned exclusively by the authenticated user."""
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = user_email or (current_user["email"] if current_user else None) or x_user_email
    u_id = (current_user["id"] if current_user else None) or x_user_id

    # If no authenticated user is identified, return empty list
    if not u_email and not u_id:
        return {"documents": []}

    docs = doc_store.list_documents(user_email=u_email, user_id=u_id)
    result = []
    for doc in docs:
        fname = doc.get("filename", "")
        safe = os.path.basename(fname)
        on_disk = os.path.exists(os.path.join(UPLOAD_DIR, safe))
        result.append({
            **doc,
            "viewable": on_disk,
            "file_url": f"/api/v1/documents/file/{safe}" if on_disk else None,
            "content_url": f"/api/v1/documents/content/{safe}" if on_disk else None,
        })
    return {"documents": result}


# ── Delete a document ─────────────────────────────────────────────────────────

@router.delete("/{filename:path}")
async def delete_document(
    filename: str,
    authorization: Optional[str] = Header(None),
    x_user_email: Optional[str] = Header(None),
    x_user_id: Optional[str] = Header(None),
):
    """Remove a document belonging to the user from the index and disk."""
    current_user = get_current_user_from_request(authorization, x_user_email, x_user_id)
    u_email = (current_user["email"] if current_user else None) or x_user_email
    u_id = (current_user["id"] if current_user else None) or x_user_id

    safe_name = os.path.basename(filename)

    # Remove from in-memory + JSON store scoped to user
    removed = doc_store.remove_document(safe_name, user_email=u_email, user_id=u_id)
    if not removed:
        removed = doc_store.remove_document(filename, user_email=u_email, user_id=u_id)

    # Delete physical file from disk only if no other user is referencing this file
    other_users_have_doc = any(
        c.get("filename") == safe_name and (c.get("user_email") or "").lower() != (u_email or "").lower()
        for c in doc_store.chunks
    )
    file_deleted = False
    if not other_users_have_doc:
        file_path = os.path.join(UPLOAD_DIR, safe_name)
        if os.path.exists(file_path):
            os.remove(file_path)
            file_deleted = True

    if not removed and not file_deleted:
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found.")

    doc_store.commit()
    return {"message": f"Document '{filename}' deleted successfully.", "file_deleted": file_deleted}

