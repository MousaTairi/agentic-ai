from __future__ import annotations

import hashlib
import importlib.util
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import COURSE


def course_module(name: str):
    spec = importlib.util.spec_from_file_location(name, COURSE / "labs" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # prepare_data uses only stdlib; no course source or generated course data is changed.
    spec.loader.exec_module(module)
    return module


class Store:
    def __init__(self, runtime: Path):
        self.runtime = runtime
        runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = runtime / "rafeeq.sqlite"
        if not self.path.exists():
            seed = course_module("prepare_data")
            seed.DATA, seed.DB_PATH, seed.INBOX_PATH = runtime, self.path, runtime / "inbox.jsonl"
            seed.build()
        self.path.chmod(0o600)
        with self.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY, history TEXT NOT NULL DEFAULT '[]', expires REAL NOT NULL,
              verified TEXT, verified_until REAL NOT NULL DEFAULT 0,
              failures INTEGER NOT NULL DEFAULT 0, requests INTEGER NOT NULL DEFAULT 0,
              window REAL NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS actions (
              id TEXT PRIMARY KEY, session_id TEXT NOT NULL, tool TEXT NOT NULL,
              args TEXT NOT NULL, status TEXT NOT NULL, expires REAL NOT NULL, result TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS active_proposal ON actions(session_id,tool,args)
              WHERE status IN ('pending','awaiting_officer');
            CREATE TABLE IF NOT EXISTS events (
              id INTEGER PRIMARY KEY, ts REAL NOT NULL, trace_id TEXT NOT NULL,
              event TEXT NOT NULL, metadata TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def new_session(self) -> str:
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute("INSERT INTO sessions(id,expires) VALUES (?,?)", (token, time.time() + 86400))
        return token

    def session(self, sid: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT * FROM sessions WHERE id=? AND expires>?", (sid, time.time())).fetchone()
        if row is None:
            raise PermissionError("Session expired. Reload the page.")
        return dict(row)

    def rate_limit(self, sid: str) -> None:
        self.session(sid)
        with self.connect() as db:
            row = db.execute("SELECT requests,window FROM sessions WHERE id=?", (sid,)).fetchone()
            count = row["requests"] if time.time() - row["window"] < 60 else 0
            if count >= 15:
                raise TimeoutError("Please wait one minute before retrying.")
            db.execute("UPDATE sessions SET requests=?,window=? WHERE id=?",
                       (count + 1, row["window"] if count else time.time(), sid))

    def authorize(self, sid: str, permit_id: str) -> None:
        session = self.session(sid)
        if session["verified"] != permit_id or session["verified_until"] < time.time():
            raise PermissionError("Verify this application's identity using the form (POL-08).")

    def event(self, trace: str, event: str, **metadata) -> None:
        # Callers pass structural metadata only, never messages, tool arguments, or tool outputs.
        with self.connect() as db:
            db.execute("INSERT INTO events(ts,trace_id,event,metadata) VALUES (?,?,?,?)",
                       (time.time(), trace, event, json.dumps(metadata)))

    @staticmethod
    def trace_session(sid: str) -> str:
        return hashlib.sha256(sid.encode()).hexdigest()[:12]
