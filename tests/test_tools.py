import json
import sqlite3

import pytest

from app.tools import query_reference_db, run_query


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "ref.db"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE term (id TEXT, name TEXT);
        INSERT INTO term VALUES ('HP:1', 'Fever'), ('HP:2', 'Chest pain'), ('HP:3', 'Cough');
        CREATE TABLE is_a (child TEXT, parent TEXT);
        INSERT INTO is_a VALUES ('HP:3', 'HP:2'), ('HP:2', 'HP:1');
    """)
    con.commit()
    con.close()
    return path


def rows_in(path):
    return sqlite3.connect(path).execute("SELECT count(*) FROM term").fetchone()[0]


def test_select_returns_columns_and_rows(db):
    out = json.loads(run_query("SELECT id, name FROM term WHERE id = 'HP:1'", db))
    assert out == {
        "columns": ["id", "name"],
        "rows": [["HP:1", "Fever"]],
        "truncated": False,
    }


def test_recursive_cte_is_allowed(db):
    sql = """WITH RECURSIVE up(id) AS (SELECT 'HP:3' UNION SELECT parent FROM is_a JOIN up ON child = up.id)
             SELECT id FROM up ORDER BY id"""
    assert json.loads(run_query(sql, db))["rows"] == [["HP:1"], ["HP:2"], ["HP:3"]]


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO term VALUES ('HP:9', 'x')",
        "DELETE FROM term",
        "DROP TABLE term",
        "UPDATE term SET name = 'x'",
        "CREATE TABLE t (x)",
    ],
)
def test_writes_are_rejected(db, sql):
    assert run_query(sql, db).startswith("SQL error")
    assert rows_in(db) == 3


def test_attach_is_rejected(db, tmp_path):
    assert run_query(f"ATTACH '{tmp_path / 'other.db'}' AS o", db).startswith(
        "SQL error"
    )
    assert not (tmp_path / "other.db").exists()


def test_pragma_is_rejected(db):
    assert run_query("PRAGMA query_only = OFF", db).startswith("SQL error")


def test_multiple_statements_are_rejected(db):
    assert run_query("SELECT 1; DELETE FROM term", db).startswith("SQL error")
    assert rows_in(db) == 3


def test_rows_are_capped(db):
    out = json.loads(run_query("SELECT * FROM term", db, max_rows=2))
    assert len(out["rows"]) == 2 and out["truncated"] is True


def test_runaway_query_is_interrupted(db):
    sql = "WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT count(*) FROM n"
    assert "time limit" in run_query(sql, db, timeout_s=0.2)


def test_huge_values_are_rejected(db):
    assert run_query("SELECT length(zeroblob(100000000))", db).startswith("SQL error")


def test_oversized_result_is_rejected(db):
    out = run_query("SELECT group_concat(name) FROM term", db, max_chars=10)
    assert out.startswith("SQL error") and "too large" in out


def test_missing_db_says_how_to_build_it(tmp_path):
    assert "make seed" in run_query("SELECT 1", tmp_path / "absent.db")
    assert not (tmp_path / "absent.db").exists()


def test_tool_takes_only_sql():
    assert set(query_reference_db.args) == {"sql"}
