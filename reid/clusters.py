"""FAISS-backed cluster store with SQLite metadata."""

import sqlite3
import time
import numpy as np
import faiss
import logging

log = logging.getLogger(__name__)

EMBEDDING_DIM = 512  # InsightFace ArcFace / buffalo_l


class ClusterDB:
    def __init__(self, db_path: str, threshold: float = 0.6):
        self.threshold = threshold
        self.db_path = db_path
        self.con = sqlite3.connect(db_path, check_same_thread=False)
        self._init_schema()
        self.index = faiss.IndexFlatIP(EMBEDDING_DIM)  # inner product = cosine on L2-normed vecs
        self.cluster_ids: list[int] = []
        self._load_index()

    def _init_schema(self):
        self.con.executescript("""
            CREATE TABLE IF NOT EXISTS clusters (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                kind      TEXT NOT NULL,  -- 'person' or 'vehicle'
                label     TEXT,           -- 'code_enforcement' or NULL for unknown
                count     INTEGER DEFAULT 1,
                first_seen REAL,
                last_seen  REAL,
                embedding  BLOB
            );
        """)
        self.con.commit()

    def _load_index(self):
        rows = self.con.execute(
            "SELECT id, embedding FROM clusters ORDER BY id"
        ).fetchall()
        for row_id, blob in rows:
            vec = np.frombuffer(blob, dtype=np.float32).copy()
            self._normalize(vec)
            self.index.add(vec.reshape(1, -1))
            self.cluster_ids.append(row_id)
        log.info("Loaded %d clusters from %s", len(self.cluster_ids), self.db_path)

    def _normalize(self, vec: np.ndarray) -> np.ndarray:
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    def match_or_create(self, kind: str, embedding: np.ndarray, label: str | None = None) -> dict:
        vec = self._normalize(embedding.copy()).reshape(1, -1).astype(np.float32)
        now = time.time()

        if self.index.ntotal > 0:
            scores, indices = self.index.search(vec, k=1)
            score = float(scores[0][0])
            if score >= self.threshold:
                cluster_id = self.cluster_ids[indices[0][0]]
                row = self.con.execute(
                    "UPDATE clusters SET count=count+1, last_seen=? WHERE id=? RETURNING id, count, label",
                    (now, cluster_id),
                ).fetchone()
                self.con.commit()
                return {"cluster_id": row[0], "count": row[1], "label": row[2], "new": False, "score": score}

        # New cluster
        blob = embedding.astype(np.float32).tobytes()
        cur = self.con.execute(
            "INSERT INTO clusters (kind, label, count, first_seen, last_seen, embedding) VALUES (?,?,1,?,?,?) RETURNING id",
            (kind, label, now, now, blob),
        )
        new_id = cur.fetchone()[0]
        self.con.commit()
        self.index.add(vec)
        self.cluster_ids.append(new_id)
        return {"cluster_id": new_id, "count": 1, "label": label, "new": True, "score": 0.0}
