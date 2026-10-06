"""A credencial AWS colada depois que a PoV subiu precisa valer sem reiniciar."""
from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import athena_side  # noqa: E402


def test_new_credentials_file_is_picked_up_without_restart(monkeypatch, tmp_path):
    creds = tmp_path / "credentials"
    creds.write_text("")
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(creds))
    monkeypatch.setenv("AWS_CONFIG_FILE", str(tmp_path / "config"))
    monkeypatch.setenv("AWS_EC2_METADATA_DISABLED", "true")
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN", "AWS_PROFILE"):
        monkeypatch.delenv(name, raising=False)

    first = athena_side.identity()
    assert first["disponivel"] is False
    assert "ausente" in first["erro"]

    creds.write_text(
        "[default]\naws_access_key_id=AKIAIOSFODNN7EXAMPLE\n"
        "aws_secret_access_key=fakefakefakefakefakefakefakefakefakefake\n"
    )
    second = athena_side.identity()
    # Credencial fake: a AWS recusa. O que importa é que o arquivo novo foi lido.
    assert second["disponivel"] is False
    assert "ausente" not in second["erro"]
