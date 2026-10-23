import re
import json
import math
from pathlib import Path
from typing import List, Dict, Any, Optional

DATA_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "doc_store.json"

class DocumentStore:
    def __init__(self):
        self.chunks: List[Dict[str, Any]] = []
        self.documents: Dict[str, Any] = {}
        self._load_from_disk()
    
    def _save_to_disk(self):
        try:
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(DATA_FILE, "w", encoding="utf-8") as f:
                json.dump({
                    "documents": self.documents,
                    "chunks": self.chunks
                }, f)
        except Exception as e:
            print(f"[DocumentStore] Failed to persist data: {e}")

    def _load_from_disk(self):
        if DATA_FILE.exists():
            try:
                with open(DATA_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    raw_documents = data.get("documents", {})
                    raw_chunks = data.get("chunks", [])

                    # Assign legacy sample documents without owner to starter demo user
                    cleaned_docs = {}
                    for key, meta in raw_documents.items():
                        fname = meta.get("filename", key)
                        u_email = meta.get("user_email")
                        if not u_email:
                            u_email = "user@docsearch.io"
                            meta["user_email"] = u_email
                        meta["filename"] = fname
                        new_key = f"{u_email.lower()}::{fname}"
                        meta["key"] = new_key
                        cleaned_docs[new_key] = meta

                    self.documents = cleaned_docs

                    seen = set()
                    clean_chunks = []
                    for c in raw_chunks:
                        u_email = c.get("user_email")
                        if not u_email:
                            u_email = "user@docsearch.io"
                            c["user_email"] = u_email
                        key = (c.get("filename"), c.get("page_number"), c.get("text", "").strip(), u_email.lower())
                        if key not in seen:
                            seen.add(key)
                            clean_chunks.append(c)
                    self.chunks = clean_chunks
                    print(f"[DocumentStore] Loaded {len(self.documents)} documents and {len(self.chunks)} chunks from disk.")
            except Exception as e:
                print(f"[DocumentStore] Failed to load data from disk: {e}")

    def _doc_key(self, filename: str, user_email: Optional[str] = None) -> str:
        clean_email = (user_email or "").strip().lower()
        return f"{clean_email}::{filename}" if clean_email else filename

    def add_document(self, filename: str, pages: int, user_email: Optional[str] = None, user_id: Optional[str] = None):
        email_clean = (user_email or "").strip().lower() if user_email else None
        key = self._doc_key(filename, email_clean)
        self.documents[key] = {
            "key": key,
            "filename": filename,
            "pages": pages,
            "status": "ready",
            "user_email": email_clean,
            "user_id": user_id
        }
        # Remove any existing chunks for this document & user to avoid duplication on re-upload
        self.chunks = [
            c for c in self.chunks 
            if not (c.get("filename") == filename and (not email_clean or (c.get("user_email") or "").lower() == email_clean))
        ]
        self._save_to_disk()
        
    def add_chunk(
        self,
        filename: str,
        page_number: int,
        text: str,
        auto_save: bool = False,
        user_email: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        text_clean = text.strip()
        email_clean = (user_email or "").strip().lower() if user_email else None

        # Prevent exact duplicate additions
        for c in self.chunks:
            if (c.get("filename") == filename and 
                c.get("page_number") == page_number and 
                c.get("text", "").strip() == text_clean and
                (c.get("user_email") or "").lower() == (email_clean or "")):
                return

        self.chunks.append({
            "filename": filename,
            "page_number": page_number,
            "text": text_clean,
            "user_email": email_clean,
            "user_id": user_id
        })
        if auto_save:
            self._save_to_disk()

    def commit(self):
        """Persist all in-memory chunks and documents to disk."""
        self._save_to_disk()

    def list_documents(self, user_email: Optional[str] = None, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List documents owned by the specified user."""
        docs = []
        email_clean = (user_email or "").strip().lower() if user_email else None

        # Strict user isolation: if no user is specified, return empty list!
        if not email_clean and not user_id:
            return []

        for key, meta in self.documents.items():
            doc_email = (meta.get("user_email") or "").strip().lower() if meta.get("user_email") else None
            doc_uid = meta.get("user_id")

            matches = False
            if email_clean and doc_email == email_clean:
                matches = True
            if user_id and doc_uid == user_id:
                matches = True
            if not matches:
                continue

            filename = meta.get("filename", key)
            doc_chunks = [
                c for c in self.chunks 
                if c.get("filename") == filename and (not email_clean or (c.get("user_email") or "").lower() == email_clean)
            ]
            doc_pages = set(c.get("page_number") for c in doc_chunks)
            docs.append({
                "filename": filename,
                "pages": meta.get("pages", len(doc_pages)),
                "indexed_pages": len(doc_pages),
                "chunks": len(doc_chunks),
                "status": meta.get("status", "ready"),
                "user_email": doc_email
            })
        return docs

    def remove_document(self, filename: str, user_email: Optional[str] = None, user_id: Optional[str] = None) -> bool:
        """Remove a document and all its chunks for the specific user."""
        email_clean = (user_email or "").strip().lower() if user_email else None
        target_key = None

        for key, meta in list(self.documents.items()):
            if meta.get("filename") == filename or key == filename:
                if email_clean:
                    if (meta.get("user_email") or "").lower() == email_clean:
                        target_key = key
                        break
                else:
                    target_key = key
                    break

        if not target_key:
            return False

        del self.documents[target_key]
        self.chunks = [
            c for c in self.chunks 
            if not (c.get("filename") == filename and (not email_clean or (c.get("user_email") or "").lower() == email_clean))
        ]
        return True

    def get_page_text(self, filename: str, page_number: int, user_email: Optional[str] = None) -> str:
        """Retrieve complete text for a given page."""
        email_clean = (user_email or "").strip().lower() if user_email else None
        page_chunks = [
            c.get("text", "") 
            for c in self.chunks 
            if c.get("filename") == filename 
            and c.get("page_number") == page_number
            and (not email_clean or (c.get("user_email") or "").lower() == email_clean)
        ]
        return "\n\n".join(page_chunks)

    def search(
        self,
        query: str,
        filenames: List[str] = None,
        top_k: int = 5,
        user_email: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        query_words = set(re.findall(r'\w+', query.lower()))
        if not query_words:
            return []

        email_clean = (user_email or "").strip().lower() if user_email else None
        scored_chunks = []

        for chunk in self.chunks:
            if email_clean and (chunk.get("user_email") or "").lower() != email_clean:
                continue
            if filenames and chunk["filename"] not in filenames:
                continue
                
            chunk_words = re.findall(r'\w+', chunk["text"].lower())
            chunk_word_set = set(chunk_words)
            
            overlap = query_words.intersection(chunk_word_set)
            if not overlap:
                continue
                
            score = len(overlap) / (math.log(len(chunk_words) + 1) + 1)
            
            scored_chunks.append({
                "chunk": chunk,
                "score": score
            })
            
        scored_chunks.sort(key=lambda x: x["score"], reverse=True)
        return scored_chunks[:top_k]

doc_store = DocumentStore()
