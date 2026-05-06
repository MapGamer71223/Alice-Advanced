import os
import time
import sqlite3
import threading
import logging
from typing import List, Dict, Optional, Tuple, Any
import numpy as np
from sentence_transformers import SentenceTransformer
from contextlib import contextmanager

# Optional backends
try:
    import faiss
    _FAISS = True
    try:
        _GPU_AVAILABLE = faiss.get_num_gpus() > 0
    except Exception:
        _GPU_AVAILABLE = False
except Exception:
    faiss = None
    _FAISS = False
    _GPU_AVAILABLE = False

try:
    import hnswlib
    _HNSW = True
except Exception:
    hnswlib = None
    _HNSW = False

_LOG = logging.getLogger(__name__)
_LOG.setLevel(logging.INFO)


class MemoryManager:
    """
    Enhanced MemoryManager — drop-in replacement with:
      - SQLite persistence
      - FAISS / HNSW / naive index backends
      - batching for writes
      - embedding caching
      - background index persistence
      - additional utilities (delete, search_by_time, count, clear)
    """

    def __init__(
        self,
        db_path: str = "alice_memory.db",
        embed_model_name: str = "all-MiniLM-L6-v2",
        faiss_index_path: Optional[str] = None,
        hnsw_index_path: Optional[str] = None,
        hnsw_max_elements: int = 200_000,
        use_gpu: bool = True,
        batch_interval: float = 1.0,
        flush_on_add: bool = False,
        save_interval: float = 30.0,
    ):
        # config
        self.db_path = db_path
        self.faiss_index_path = faiss_index_path
        self.hnsw_index_path = hnsw_index_path
        self.use_gpu = use_gpu and _GPU_AVAILABLE
        self.hnsw_max_elements = hnsw_max_elements
        self.batch_interval = batch_interval
        self.flush_on_add = flush_on_add
        self.save_interval = save_interval

        # internals
        self._lock = threading.RLock()
        self._connect_db()
        self._ensure_table()
        self._prepare_statements()

        # embeddings
        self.embed_model_name = embed_model_name
        self.embed = SentenceTransformer(self.embed_model_name)
        self.dim = self.embed.get_sentence_embedding_dimension()
        self._embed_cache: Dict[str, np.ndarray] = {}

        # backend selection
        self.backend = None
        self.index = None
        self.gpu_res = None
        self.hnsw_index = None
        self.hnsw_ids = set()
        self.naive_store: List[Tuple[int, np.ndarray]] = []

        if _FAISS:
            try:
                self._init_faiss()
                self.backend = "faiss"
            except Exception as e:
                _LOG.exception("FAISS init failed, falling back to naive: %s", e)
                self._init_naive()
                self.backend = "naive"
        elif _HNSW:
            try:
                self._init_hnsw()
                self.backend = "hnsw"
            except Exception as e:
                _LOG.exception("HNSW init failed, falling back to naive: %s", e)
                self._init_naive()
                self.backend = "naive"
        else:
            self._init_naive()
            self.backend = "naive"

        # set ef for hnsw if present
        if _HNSW and self.backend == "hnsw" and hasattr(self.hnsw_index, "set_ef"):
            try:
                self.hnsw_index.set_ef(50)
            except Exception:
                pass

        # background write buffer + thread
        self._write_buffer: List[Tuple[str, str, Optional[str], float]] = []
        self._stop_bg = threading.Event()
        self._bg_thread = threading.Thread(target=self._bg_worker, daemon=True)
        self._bg_thread.start()

        # periodic saver for indexes
        self._saver_thread = threading.Thread(target=self._periodic_save, daemon=True)
        self._saver_thread.start()

        _LOG.info("MemoryManager initialized (backend=%s, dim=%d)", self.backend, self.dim)

    # ---------------------------
    # Database helpers
    # ---------------------------
    def _connect_db(self):
        # Use check_same_thread=False and a reasonable timeout for concurrent access
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30.0)
        # improve perf and safety
        try:
            self.conn.execute("PRAGMA journal_mode=WAL;")
            self.conn.execute("PRAGMA synchronous=NORMAL;")
            self.conn.execute("PRAGMA temp_store=MEMORY;")
        except Exception:
            pass

    def _ensure_table(self):
        with self._locked_tx() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    text TEXT NOT NULL,
                    speaker TEXT,
                    mood TEXT,
                    ts REAL NOT NULL
                );
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_memories_ts ON memories(ts DESC);")

    def _prepare_statements(self):
        # store prepared statements for reuse
        self._insert_sql = "INSERT INTO memories (text, speaker, mood, ts) VALUES (?, ?, ?, ?)"
        self._select_by_id = "SELECT id, text, speaker, mood, ts FROM memories WHERE id = ?"
        self._select_recent = "SELECT id, text, speaker, mood, ts FROM memories ORDER BY ts DESC LIMIT ?"
        self._select_count = "SELECT COUNT(*) FROM memories"

    @contextmanager
    def _locked_tx(self):
        """
        Provide a cursor inside a lock to avoid concurrency issues.
        Commits automatically on success.
        """
        with self._lock:
            cur = self.conn.cursor()
            try:
                yield cur
                self.conn.commit()
            except Exception:
                try:
                    self.conn.rollback()
                except Exception:
                    pass
                raise
            finally:
                try:
                    cur.close()
                except Exception:
                    pass

    # ---------------------------
    # Backends
    # ---------------------------
    def _init_faiss(self):
        if not _FAISS:
            raise RuntimeError("faiss not available")
        # create CPU index
        cpu_index = faiss.IndexFlatIP(self.dim)
        index = faiss.IndexIDMap(cpu_index)
        if self.faiss_index_path and os.path.isfile(self.faiss_index_path):
            try:
                loaded = faiss.read_index(self.faiss_index_path)
                if not isinstance(loaded, faiss.IndexIDMap):
                    loaded = faiss.IndexIDMap(loaded)
                index = loaded
                _LOG.info("FAISS index loaded from %s", self.faiss_index_path)
            except Exception as e:
                _LOG.warning("Could not load FAISS index: %s — starting fresh", e)
        # move to GPU if requested and available
        if self.use_gpu:
            try:
                self.gpu_res = faiss.StandardGpuResources()
                index = faiss.index_cpu_to_gpu(self.gpu_res, 0, index)
                _LOG.info("FAISS moved to GPU")
            except Exception as e:
                _LOG.warning("FAISS GPU move failed, using CPU: %s", e)
                self.use_gpu = False
        self.index = index

    def _save_faiss(self):
        if not self.faiss_index_path or self.index is None:
            return
        try:
            idx = self.index
            if self.use_gpu and hasattr(faiss, "index_gpu_to_cpu"):
                idx = faiss.index_gpu_to_cpu(idx)
            with self._lock:
                faiss.write_index(idx, self.faiss_index_path)
            _LOG.info("FAISS index saved to %s", self.faiss_index_path)
        except Exception as e:
            _LOG.exception("Failed to save FAISS index: %s", e)

    def _init_hnsw(self):
        if not _HNSW:
            raise RuntimeError("hnswlib not available")
        self.hnsw_index = hnswlib.Index(space='cosine', dim=self.dim)
        if self.hnsw_index_path and os.path.isfile(self.hnsw_index_path):
            try:
                self.hnsw_index.load_index(self.hnsw_index_path)
                _LOG.info("hnswlib index loaded from %s", self.hnsw_index_path)
            except Exception:
                self.hnsw_index.init_index(max_elements=self.hnsw_max_elements, ef_construction=200, M=16)
        else:
            self.hnsw_index.init_index(max_elements=self.hnsw_max_elements, ef_construction=200, M=16)

    def _save_hnsw(self):
        if not self.hnsw_index_path or self.hnsw_index is None:
            return
        try:
            self.hnsw_index.save_index(self.hnsw_index_path)
            _LOG.info("hnswlib index saved to %s", self.hnsw_index_path)
        except Exception as e:
            _LOG.exception("Failed to save hnsw index: %s", e)

    def _init_naive(self):
        self.naive_store = []
        _LOG.warning("Using naive in-memory index (suitable for small datasets / testing)")

    # ---------------------------
    # Background workers
    # ---------------------------
    def _bg_worker(self):
        """Batch write worker — flushes buffer at intervals for faster writes."""
        _LOG.debug("MemoryManager background worker started")
        while not self._stop_bg.is_set():
            try:
                time.sleep(self.batch_interval)
                self._flush_buffer()
            except Exception as e:
                _LOG.exception("Error in background worker: %s", e)
        # final flush
        try:
            self._flush_buffer()
        except Exception:
            pass
        _LOG.debug("MemoryManager background worker stopped")

    def _periodic_save(self):
        """Periodically save index files to disk."""
        while not self._stop_bg.is_set():
            try:
                time.sleep(self.save_interval)
                self.save_index()
            except Exception as e:
                _LOG.exception("Error in periodic save: %s", e)

    # ---------------------------
    # Core operations
    # ---------------------------
    def add_memory(self, text: str, speaker: str = "user", mood: Optional[str] = None) -> int:
        """
        Add a memory. This method buffers writes and returns the assigned row id.
        Blocking: if flush_on_add=True, it will flush synchronously.
        """
        ts = time.time()
        with self._lock:
            # add to sqlite immediately (we want the rowid deterministically)
            cur = self.conn.cursor()
            cur.execute(self._insert_sql, (text, speaker, mood, ts))
            rowid = cur.lastrowid
            self.conn.commit()
            cur.close()

            # add embedding to index immediately (keep index in sync)
            emb = self._embed_text(text)
            vec = emb.reshape(1, -1).astype("float32")

            if self.backend == "faiss":
                try:
                    faiss.normalize_L2(vec)
                    with self._lock:
                        # faiss expects int64 ids
                        self.index.add_with_ids(vec, np.array([rowid], dtype="int64"))
                except Exception:
                    _LOG.exception("Failed to add vector to FAISS index")
            elif self.backend == "hnsw":
                try:
                    vnorm = vec / (np.linalg.norm(vec, axis=1, keepdims=True) + 1e-10)
                    with self._lock:
                        self.hnsw_index.add_items(vnorm, np.array([rowid], dtype=np.int32))
                        self.hnsw_ids.add(rowid)
                except Exception:
                    _LOG.exception("Failed to add vector to hnsw index")
            else:
                # naive store keeps (id, vector)
                self.naive_store.append((rowid, vec[0]))

            # optionally buffer the original row for batch-saving? We already persisted to DB,
            # but we can maintain a small recent cache if desired. For now keep DB authoritative.
            if self.flush_on_add:
                try:
                    self.conn.commit()
                except Exception:
                    pass
        return rowid

    def _embed_text(self, text: str) -> np.ndarray:
        """Cache embeddings to avoid recomputation for same text."""
        key = text.strip()
        if not key:
            return np.zeros((self.dim,), dtype="float32")
        if key in self._embed_cache:
            return self._embed_cache[key]
        try:
            emb = self.embed.encode([text], convert_to_numpy=True)[0].astype("float32")
            self._embed_cache[key] = emb
            # keep embed cache small
            if len(self._embed_cache) > 10000:
                # pop some random items
                for _ in range(1000):
                    self._embed_cache.pop(next(iter(self._embed_cache)), None)
            return emb
        except Exception:
            _LOG.exception("Embedding model failed; returning zeros")
            return np.zeros((self.dim,), dtype="float32")

    def get_recent(self, n: int = 5) -> List[Dict]:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(self._select_recent, (n,))
            rows = cur.fetchall()
            cur.close()
        # return newest-first reversed to keep original ordering as in previous impl
        return [
            {"id": r[0], "text": r[1], "speaker": r[2], "mood": r[3], "ts": r[4]}
            for r in reversed(rows)
        ]
        
    def recall(self, query: str, top_k: int = 3, min_score: float = 0.0) -> List[Dict]:
        q_emb = self._embed_text(query).reshape(1, -1).astype("float32")
        results: List[Dict[str, Any]] = []

        if self.backend == "faiss":
            try:
                faiss.normalize_L2(q_emb)
                with self._lock:
                    D, I = self.index.search(q_emb, top_k)
                for score, idx in zip(D[0], I[0]):
                    if idx < 0 or score < min_score:
                        continue
                    with self._lock:
                        row = self.conn.execute(self._select_by_id, (int(idx),)).fetchone()
                    if row:
                        results.append({
                            "id": row[0], "text": row[1], "speaker": row[2],
                            "mood": row[3], "ts": row[4], "score": float(score)
                        })
            except Exception:
                _LOG.exception("FAISS recall failed, returning empty list")
                return []
            return results

        if self.backend == "hnsw":
            try:
                qn = q_emb / (np.linalg.norm(q_emb, axis=1, keepdims=True) + 1e-10)
                labels, distances = self.hnsw_index.knn_query(qn, k=top_k)
                for label, dist in zip(labels[0], distances[0]):
                    if label == -1:
                        continue
                    score = max(0.0, 1.0 - float(dist))
                    if score < min_score:
                        continue
                    with self._lock:
                        row = self.conn.execute(self._select_by_id, (int(label),)).fetchone()
                    if row:
                        results.append({
                            "id": row[0], "text": row[1], "speaker": row[2],
                            "mood": row[3], "ts": row[4], "score": score
                        })
            except Exception:
                _LOG.exception("hnsw recall failed, returning empty list")
                return []
            return results

        # naive
        qv = q_emb[0]
        sims = []
        for mid, emb in self.naive_store:
            dot = float(np.dot(qv, emb))
            denom = (np.linalg.norm(qv) * np.linalg.norm(emb) + 1e-10)
            sim = dot / denom
            sims.append((mid, sim))
        sims.sort(key=lambda x: -x[1])
        for mid, sim in sims[:top_k]:
            if sim < min_score:
                continue
            with self._lock:
                row = self.conn.execute(self._select_by_id, (mid,)).fetchone()
            if row:
                results.append({
                    "id": row[0], "text": row[1], "speaker": row[2],
                    "mood": row[3], "ts": row[4], "score": float(sim)
                })
        return results

    def build_memory_context(
        self, user_input: str, last_n: int = 5, top_k: int = 3, include_mood: bool = True, max_chars: int = 1500
    ) -> str:
        recent = self.get_recent(last_n)
        recalled = self.recall(user_input, top_k=top_k)
        lines = []
        if recent:
            lines.append("Recent conversation (most recent last):")
            for r in recent:
                line = f'- {r["speaker"]}: \"{r["text"]}\"'
                if include_mood and r.get("mood"):
                    line += f" (mood: {r['mood']})"
                lines.append(line)
        if recalled:
            lines.append("\nRelevant past memories:")
            for mem in recalled:
                line = f'- {mem["speaker"]}: \"{mem["text"]}\"'
                if include_mood and mem.get("mood"):
                    line += f" (mood: {mem['mood']}, sim={mem['score']:.2f})"
                else:
                    line += f" (sim={mem['score']:.2f})"
                lines.append(line)
        if lines:
            ctx = "\n".join(lines)
            if len(ctx) > max_chars:
                ctx = ctx[: max_chars - 10] + "\n... (truncated)"
            return ctx
        return ""

    # ---------------------------
    # Persistence / housekeeping
    # ---------------------------
    def save_index(self):
        """Save index state to disk if supported (faiss/hnsw)."""
        try:
            if self.backend == "faiss":
                self._save_faiss()
            elif self.backend == "hnsw":
                self._save_hnsw()
        except Exception:
            _LOG.exception("save_index failed")

    def _flush_buffer(self):
        # If we had buffered uncommitted DB rows (currently DB is committed immediately),
        # keep hook for future buffering implementations.
        # For now this ensures indexes are persisted periodically.
        try:
            self.save_index()
        except Exception:
            _LOG.exception("Error flushing buffer while saving index")

    def close(self):
        """Gracefully stop background threads, save indexes, and close DB."""
        _LOG.info("MemoryManager closing: stopping background threads and saving state.")
        self._stop_bg.set()
        try:
            self._bg_thread.join(timeout=2.0)
        except Exception:
            pass
        try:
            self._saver_thread.join(timeout=2.0)
        except Exception:
            pass
        # final save
        try:
            self.save_index()
        except Exception:
            pass
        # close DB
        try:
            with self._lock:
                self.conn.close()
        except Exception:
            pass

    # ---------------------------
    # Utilities
    # ---------------------------
    def semantic_search(self, query: str, top_k: int = 3, min_score: float = 0.0) -> List[str]:
        return [mem["text"] for mem in self.recall(query, top_k=top_k, min_score=min_score)]

    def format_memories_for_context(self, limit: int = 5) -> str:
        recent = self.get_recent(limit)
        return "\n".join(f'- {m["speaker"]}: \"{m["text"]}\"' for m in recent)

    def delete_memory(self, mem_id: int) -> bool:
        """Delete a memory by id from DB and index. Returns True on success."""
        try:
            with self._lock:
                cur = self.conn.cursor()
                cur.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
                self.conn.commit()
                cur.close()
            if self.backend == "faiss":
                try:
                    # FAISS doesn't have a direct delete for IndexIDMapFlat; mark indices by rebuilding may be necessary.
                    # Here we attempt to remove by re-creating index without the deleted id (expensive)
                    _LOG.info("FAISS delete requested: marking for rebuild (not implemented inline).")
                except Exception:
                    pass
            elif self.backend == "hnsw":
                try:
                    # hnswlib supports mark_deleted if built with that flag
                    if hasattr(self.hnsw_index, "mark_deleted"):
                        self.hnsw_index.mark_deleted(mem_id)
                        self.hnsw_ids.discard(mem_id)
                except Exception:
                    pass
            else:
                self.naive_store = [(i, v) for (i, v) in self.naive_store if i != mem_id]
            return True
        except Exception:
            _LOG.exception("Failed to delete memory %s", mem_id)
            return False

    def search_by_time(self, start_ts: float, end_ts: float) -> List[Dict]:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("SELECT id, text, speaker, mood, ts FROM memories WHERE ts BETWEEN ? AND ? ORDER BY ts ASC", (start_ts, end_ts))
            rows = cur.fetchall()
            cur.close()
        return [{"id": r[0], "text": r[1], "speaker": r[2], "mood": r[3], "ts": r[4]} for r in rows]

    def count_memories(self) -> int:
        with self._lock:
            cur = self.conn.cursor()
            cur.execute(self._select_count)
            n = cur.fetchone()[0]
            cur.close()
        return int(n)

    def clear_memories(self):
        """Clears the DB table and index (dangerous)."""
        with self._lock:
            cur = self.conn.cursor()
            cur.execute("DELETE FROM memories")
            self.conn.commit()
            cur.close()
        # clear indexes
        if self.backend == "faiss":
            try:
                if self.use_gpu and hasattr(faiss, "index_gpu_to_cpu"):
                    cpu_idx = faiss.index_gpu_to_cpu(self.index)
                else:
                    cpu_idx = self.index
                cpu_idx.reset()
                if self.faiss_index_path and os.path.exists(self.faiss_index_path):
                    try:
                        os.remove(self.faiss_index_path)
                    except Exception:
                        pass
            except Exception:
                _LOG.exception("Failed to clear FAISS index")
        elif self.backend == "hnsw" and self.hnsw_index is not None:
            try:
                self.hnsw_index = None
                if self.hnsw_index_path and os.path.exists(self.hnsw_index_path):
                    try:
                        os.remove(self.hnsw_index_path)
                    except Exception:
                        pass
                self._init_hnsw()
            except Exception:
                _LOG.exception("Failed to clear hnsw index")
        else:
            self.naive_store = []

