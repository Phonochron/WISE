"""SQLite storage for analyzed imports and their history."""

import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd


def _connect(database_path: str | Path) -> sqlite3.Connection:
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _initialize(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS dataset_imports (
            id INTEGER PRIMARY KEY,
            filename TEXT NOT NULL,
            imported_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            row_count INTEGER NOT NULL
        );
        CREATE TABLE IF NOT EXISTS product_records (
            import_id INTEGER NOT NULL REFERENCES dataset_imports(id),
            row_number INTEGER NOT NULL,
            analyzed_json TEXT NOT NULL,
            PRIMARY KEY (import_id, row_number)
        );
        CREATE TABLE IF NOT EXISTS recommendation_reviews (
            import_id INTEGER NOT NULL,
            row_number INTEGER NOT NULL,
            action_key TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            PRIMARY KEY (import_id, row_number, action_key),
            FOREIGN KEY (import_id, row_number) REFERENCES product_records(import_id, row_number)
        );
        CREATE TABLE IF NOT EXISTS review_events (
            id INTEGER PRIMARY KEY,
            import_id INTEGER NOT NULL,
            row_number INTEGER NOT NULL,
            action_key TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            changed_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            FOREIGN KEY (import_id, row_number) REFERENCES product_records(import_id, row_number)
        );
        CREATE TABLE IF NOT EXISTS product_outcomes (
            import_id INTEGER NOT NULL,
            row_number INTEGER NOT NULL,
            outcome_date TEXT NOT NULL,
            sold_units INTEGER NOT NULL,
            donated_units INTEGER NOT NULL,
            redistributed_units INTEGER NOT NULL,
            wasted_units INTEGER NOT NULL,
            revenue_value REAL,
            waste_value REAL,
            note TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            PRIMARY KEY (import_id, row_number),
            FOREIGN KEY (import_id, row_number) REFERENCES product_records(import_id, row_number)
        );
        CREATE TABLE IF NOT EXISTS outcome_events (
            id INTEGER PRIMARY KEY,
            import_id INTEGER NOT NULL,
            row_number INTEGER NOT NULL,
            outcome_json TEXT NOT NULL,
            recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            FOREIGN KEY (import_id, row_number) REFERENCES product_records(import_id, row_number)
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('admin', 'branch')),
            branch TEXT,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            CHECK((role = 'admin' AND branch IS NULL) OR (role = 'branch' AND branch IS NOT NULL))
        );
        CREATE TABLE IF NOT EXISTS signup_requests (
            id INTEGER PRIMARY KEY,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            branch TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        );
        CREATE TABLE IF NOT EXISTS import_model_versions (
            import_id INTEGER PRIMARY KEY REFERENCES dataset_imports(id),
            artifact_sha256 TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS model_evaluations (
            id INTEGER PRIMARY KEY,
            evaluated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
            source_name TEXT NOT NULL,
            artifact_sha256 TEXT NOT NULL,
            evaluation_kind TEXT NOT NULL,
            metrics_json TEXT NOT NULL
        );
    """)


def save_analysis(database_path: str | Path, filename: str, analyzed: pd.DataFrame, model_sha256: str | None = None) -> int:
    records = json.loads(analyzed.to_json(orient="records", double_precision=15))
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        with connection:
            cursor = connection.execute(
                "INSERT INTO dataset_imports (filename, row_count) VALUES (?, ?)",
                (filename, len(records)),
            )
            import_id = cursor.lastrowid
            connection.executemany(
                "INSERT INTO product_records (import_id, row_number, analyzed_json) VALUES (?, ?, ?)",
                ((import_id, index, json.dumps(record, ensure_ascii=False)) for index, record in enumerate(records)),
            )
            if model_sha256 is not None:
                connection.execute(
                    "INSERT INTO import_model_versions (import_id, artifact_sha256) VALUES (?, ?)",
                    (import_id, model_sha256),
                )
    return import_id


def list_prediction_summaries(database_path: str | Path, branch: str | None = None, limit: int = 12) -> list[dict]:
    """Aggregate scored import batches without loading every product into Python."""
    batches = list_imports(database_path, branch)[:limit]
    if not batches:
        return []
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        for batch in batches:
            where = "p.import_id = ?"
            parameters: tuple = (batch["id"],)
            if branch is not None:
                where += " AND json_extract(p.analyzed_json, '$.Branch') = ?"
                parameters += (branch,)
            row = connection.execute(
                f"""SELECT AVG(CAST(json_extract(p.analyzed_json, '$.waste_proba') AS REAL)) AS average_probability,
                           SUM(json_extract(p.analyzed_json, '$.risk_level') = 'High') AS high_count,
                           SUM(json_extract(p.analyzed_json, '$.risk_level') = 'Medium') AS medium_count,
                           SUM(json_extract(p.analyzed_json, '$.risk_level') = 'Low') AS low_count
                    FROM product_records AS p WHERE {where}""",
                parameters,
            ).fetchone()
            version = connection.execute(
                "SELECT artifact_sha256 FROM import_model_versions WHERE import_id = ?",
                (batch["id"],),
            ).fetchone()
            batch.update({
                "average_probability": round(row["average_probability"], 4) if row["average_probability"] is not None else None,
                "high_count": row["high_count"] or 0,
                "medium_count": row["medium_count"] or 0,
                "low_count": row["low_count"] or 0,
                "high_rate": round((row["high_count"] or 0) / batch["row_count"], 4),
                "model_sha256": version["artifact_sha256"] if version else None,
            })
    return batches


def save_model_evaluation(database_path: str | Path, report: dict) -> int:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        with connection:
            cursor = connection.execute(
                """INSERT INTO model_evaluations (source_name, artifact_sha256, evaluation_kind, metrics_json)
                   VALUES (?, ?, ?, ?)""",
                (report["file"], report["model_sha256"], report["evaluation_kind"],
                 json.dumps(report["metrics"], ensure_ascii=False)),
            )
            return cursor.lastrowid


def list_model_evaluations(database_path: str | Path, limit: int = 12) -> list[dict]:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        rows = connection.execute(
            """SELECT id, evaluated_at, source_name, artifact_sha256, evaluation_kind, metrics_json
               FROM model_evaluations ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [{**dict(row), "metrics": json.loads(row["metrics_json"])} for row in rows]


def list_imports(database_path: str | Path, branch: str | None = None) -> list[dict]:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        if branch is None:
            rows = connection.execute(
                "SELECT id, filename, imported_at, row_count FROM dataset_imports ORDER BY id DESC"
            ).fetchall()
        else:
            rows = connection.execute(
                """SELECT i.id, i.imported_at,
                          (SELECT COUNT(*) FROM product_records AS p WHERE p.import_id = i.id
                           AND json_extract(p.analyzed_json, '$.Branch') = ?) AS row_count
                   FROM dataset_imports AS i
                   WHERE EXISTS (SELECT 1 FROM product_records AS p WHERE p.import_id = i.id
                                 AND json_extract(p.analyzed_json, '$.Branch') = ?)
                   ORDER BY i.id DESC""",
                (branch, branch),
            ).fetchall()
    return [dict(row) for row in rows]


def get_active_import(database_path: str | Path) -> dict | None:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        row = connection.execute(
            "SELECT id, filename, imported_at, row_count FROM dataset_imports ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_import(database_path: str | Path, import_id: int) -> dict | None:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        row = connection.execute(
            "SELECT id, filename, imported_at, row_count FROM dataset_imports WHERE id = ?",
            (import_id,),
        ).fetchone()
    return dict(row) if row else None


def load_active_analysis(database_path: str | Path) -> pd.DataFrame | None:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        active = connection.execute("SELECT id FROM dataset_imports ORDER BY id DESC LIMIT 1").fetchone()
        if active is None:
            return None
        rows = connection.execute(
            "SELECT analyzed_json FROM product_records WHERE import_id = ? ORDER BY row_number",
            (active["id"],),
        ).fetchall()
    return pd.DataFrame([json.loads(row["analyzed_json"]) for row in rows])


def get_product_record(database_path: str | Path, import_id: int, row_number: int) -> dict | None:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        row = connection.execute(
            """SELECT p.analyzed_json, i.filename, i.imported_at
               FROM product_records AS p
               JOIN dataset_imports AS i ON i.id = p.import_id
               WHERE p.import_id = ? AND p.row_number = ?""",
            (import_id, row_number),
        ).fetchone()
    if row is None:
        return None
    return {"product": json.loads(row["analyzed_json"]), "filename": row["filename"], "imported_at": row["imported_at"]}


def get_product_reviews(database_path: str | Path, import_id: int, row_number: int) -> tuple[dict, list[dict]]:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        current = connection.execute(
            "SELECT action_key, status, note, updated_at FROM recommendation_reviews WHERE import_id = ? AND row_number = ?",
            (import_id, row_number),
        ).fetchall()
        history = connection.execute(
            """SELECT action_key, status, note, changed_at FROM review_events
               WHERE import_id = ? AND row_number = ? ORDER BY id DESC""",
            (import_id, row_number),
        ).fetchall()
    return {row["action_key"]: dict(row) for row in current}, [dict(row) for row in history]


def save_product_review(
    database_path: str | Path, import_id: int, row_number: int,
    action_key: str, status: str, note: str,
) -> None:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        with connection:
            connection.execute(
                """INSERT INTO recommendation_reviews (import_id, row_number, action_key, status, note)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(import_id, row_number, action_key) DO UPDATE SET
                   status = excluded.status, note = excluded.note,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
                (import_id, row_number, action_key, status, note),
            )
            connection.execute(
                "INSERT INTO review_events (import_id, row_number, action_key, status, note) VALUES (?, ?, ?, ?, ?)",
                (import_id, row_number, action_key, status, note),
            )


def get_product_outcome(database_path: str | Path, import_id: int, row_number: int) -> tuple[dict | None, list[dict]]:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        current = connection.execute(
            "SELECT * FROM product_outcomes WHERE import_id = ? AND row_number = ?",
            (import_id, row_number),
        ).fetchone()
        history = connection.execute(
            """SELECT outcome_json, recorded_at FROM outcome_events
               WHERE import_id = ? AND row_number = ? ORDER BY id DESC""",
            (import_id, row_number),
        ).fetchall()
    events = [{**json.loads(row["outcome_json"]), "recorded_at": row["recorded_at"]} for row in history]
    return dict(current) if current else None, events


def save_product_outcome(database_path: str | Path, import_id: int, row_number: int, outcome: dict) -> None:
    columns = ("outcome_date", "sold_units", "donated_units", "redistributed_units", "wasted_units", "revenue_value", "waste_value", "note")
    values = tuple(outcome[column] for column in columns)
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        with connection:
            connection.execute(
                """INSERT INTO product_outcomes
                   (import_id, row_number, outcome_date, sold_units, donated_units, redistributed_units,
                    wasted_units, revenue_value, waste_value, note)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(import_id, row_number) DO UPDATE SET
                   outcome_date = excluded.outcome_date,
                   sold_units = excluded.sold_units, donated_units = excluded.donated_units,
                   redistributed_units = excluded.redistributed_units, wasted_units = excluded.wasted_units,
                   revenue_value = excluded.revenue_value, waste_value = excluded.waste_value,
                   note = excluded.note,
                   updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')""",
                (import_id, row_number, *values),
            )
            connection.execute(
                "INSERT INTO outcome_events (import_id, row_number, outcome_json) VALUES (?, ?, ?)",
                (import_id, row_number, json.dumps(outcome, ensure_ascii=False)),
            )


def list_outcomes(database_path: str | Path, import_id: int, branch: str | None = None) -> tuple[list[dict], int]:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        rows = connection.execute(
            """SELECT o.*, p.analyzed_json FROM product_outcomes AS o
               JOIN product_records AS p ON p.import_id = o.import_id AND p.row_number = o.row_number
               WHERE o.import_id = ? ORDER BY o.outcome_date DESC, o.row_number""",
            (import_id,),
        ).fetchall()
        completed_rows = connection.execute(
            """SELECT p.analyzed_json FROM recommendation_reviews AS r
               JOIN product_records AS p ON p.import_id = r.import_id AND p.row_number = r.row_number
               WHERE r.import_id = ? AND r.status = 'completed'""",
            (import_id,),
        ).fetchall()
    completed = sum(branch is None or json.loads(row["analyzed_json"]).get("Branch") == branch for row in completed_rows)
    result = []
    for row in rows:
        item = dict(row)
        product = json.loads(item.pop("analyzed_json"))
        if branch is not None and product.get("Branch") != branch:
            continue
        item.update({key: product.get(key) for key in ("Product_ID", "Product_Name", "Branch", "Category")})
        result.append(item)
    return result, completed


def save_user(database_path: str | Path, username: str, password_hash: str, role: str, branch: str | None) -> None:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        with connection:
            connection.execute(
                """INSERT INTO users (username, password_hash, role, branch) VALUES (?, ?, ?, ?)
                   ON CONFLICT(username) DO UPDATE SET password_hash=excluded.password_hash,
                   role=excluded.role, branch=excluded.branch""",
                (username, password_hash, role, branch),
            )


def create_signup_request(database_path: str | Path, username: str, password_hash: str, branch: str) -> bool:
    """Queue a branch account for review; never grant data access here."""
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        with connection:
            if connection.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone():
                return False
            try:
                connection.execute(
                    "INSERT INTO signup_requests (username, password_hash, branch) VALUES (?, ?, ?)",
                    (username, password_hash, branch),
                )
            except sqlite3.IntegrityError:
                return False
    return True


def list_signup_requests(database_path: str | Path) -> list[dict]:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        rows = connection.execute(
            "SELECT id, username, branch, created_at FROM signup_requests ORDER BY id"
        ).fetchall()
    return [dict(row) for row in rows]


def resolve_signup_request(database_path: str | Path, request_id: int, approve: bool) -> bool:
    """Atomically approve as a branch user or discard a pending request."""
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        with connection:
            row = connection.execute(
                "SELECT username, password_hash, branch FROM signup_requests WHERE id = ?", (request_id,)
            ).fetchone()
            if row is None:
                return False
            if approve:
                try:
                    connection.execute(
                        "INSERT INTO users (username, password_hash, role, branch) VALUES (?, ?, 'branch', ?)",
                        (row["username"], row["password_hash"], row["branch"]),
                    )
                except sqlite3.IntegrityError:
                    return False
            connection.execute("DELETE FROM signup_requests WHERE id = ?", (request_id,))
    return True


def get_user_by_name(database_path: str | Path, username: str) -> dict | None:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        row = connection.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    return dict(row) if row else None


def get_user_by_id(database_path: str | Path, user_id: int) -> dict | None:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        row = connection.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return dict(row) if row else None


def list_users(database_path: str | Path) -> list[dict]:
    """List account metadata without exposing password hashes to templates."""
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        rows = connection.execute(
            "SELECT id, username, role, branch, created_at FROM users ORDER BY role, username"
        ).fetchall()
    return [dict(row) for row in rows]


def count_users(database_path: str | Path, role: str | None = None) -> int:
    with closing(_connect(database_path)) as connection:
        _initialize(connection)
        if role is None:
            return connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return connection.execute("SELECT COUNT(*) FROM users WHERE role = ?", (role,)).fetchone()[0]
