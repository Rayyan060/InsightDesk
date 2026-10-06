"""Command-line scripts: load_accounts (judge path), init_db, validate_data, generate_data, inspect_data."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.cli import generate_data, init_db, inspect_data, load_accounts, validate_data
from app.core.config import PROJECT_ROOT


def _judge_dir(tmp_path: Path) -> Path:
    d = tmp_path / "test_accounts"
    d.mkdir()
    (d / "accounts.csv").write_text(
        "account_id,company_name,owner_email,plan,status,product_version,created_at\n"
        "A9001,Judge Co,judge@example.com,Pro,active,4.3,2026-01-10\n",
        encoding="utf-8",
    )
    (d / "invoices.csv").write_text(
        "invoice_id,account_id,amount,currency,charged_on,status,failure_reason,card_last4\n"
        "INV-J001,A9001,49.0,USD,2026-09-22,paid,,4242\n",
        encoding="utf-8",
    )
    return d


def test_load_accounts_judge_flow(tmp_path, capsys) -> None:
    db = tmp_path / "judge.db"
    report = tmp_path / "report.json"
    assert load_accounts.main(["--dir", str(_judge_dir(tmp_path)), "--db", str(db), "--report", str(report)]) == 0
    out = capsys.readouterr().out
    assert "COMMITTED" in out and "judge@example.com" not in out
    assert json.loads(report.read_text())["committed"] is True
    # Repeatable: second run succeeds with everything unchanged.
    assert load_accounts.main(["--dir", str(tmp_path / "test_accounts"), "--db", str(db)]) == 0


def test_load_accounts_rejects_bad_data_with_exit_1(tmp_path, capsys) -> None:
    d = _judge_dir(tmp_path)
    (d / "invoices.csv").write_text(
        "invoice_id,account_id,amount,currency,charged_on,status,failure_reason,card_last4\nINV-J002,A9999,49.0,USD,2026-09-22,paid,,4242\n",
        encoding="utf-8",
    )
    assert load_accounts.main(["--dir", str(d), "--db", str(tmp_path / "x.db")]) == 1
    assert "account that does not exist" in capsys.readouterr().out


def test_overwrite_needs_explicit_flag(tmp_path) -> None:
    with pytest.raises(SystemExit) as excinfo:
        load_accounts.main(["--dir", str(_judge_dir(tmp_path)), "--db", str(tmp_path / "x.db"), "--on-conflict", "overwrite"])
    assert excinfo.value.code == 2


def test_init_db_is_repeatable(tmp_path, capsys) -> None:
    db = str(tmp_path / "init.db")
    assert init_db.main(["--db", db]) == 0
    assert init_db.main(["--db", db, "--with-synthetic"]) == 0
    assert init_db.main(["--db", db, "--with-synthetic"]) == 0
    out = capsys.readouterr().out
    assert "matches Annex C" in out and "accounts=36" in out


def test_validate_data_on_committed_dataset(capsys) -> None:
    assert validate_data.main(["--no-report"]) == 0
    assert "PASS" in capsys.readouterr().out


def test_validate_data_judge_mode(tmp_path, capsys) -> None:
    assert validate_data.main(["--mode", "judge", "--dir", str(_judge_dir(tmp_path))]) == 0


def test_generate_data_refuses_to_overwrite_committed_dataset(capsys) -> None:
    assert generate_data.main([]) == 1
    assert "refusing to overwrite" in capsys.readouterr().out


def test_generate_data_into_new_directory(tmp_path) -> None:
    assert generate_data.main(["--out", str(tmp_path / "gen")]) == 0


def test_inspect_masks_email(tmp_path, capsys) -> None:
    db = tmp_path / "inspect.db"
    load_accounts.main(["--dir", str(_judge_dir(tmp_path)), "--db", str(db)])
    capsys.readouterr()
    assert inspect_data.main(["--db", str(db), "--account", "A9001"]) == 0
    out = capsys.readouterr().out
    assert "j***@example.com" in out and "judge@example.com" not in out


def test_script_wrapper_runs_from_repo_root(tmp_path) -> None:
    result = subprocess.run(
        [sys.executable, "scripts/load_accounts.py", "--dir", str(_judge_dir(tmp_path)), "--db", str(tmp_path / "w.db")],
        cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
