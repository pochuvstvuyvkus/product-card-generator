import json

from card_gen.__main__ import EXIT_CONFIG, EXIT_INPUT, main

from .conftest import EXAMPLES


def test_check_only_needs_no_key(capsys, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    code = main([str(EXAMPLES / "manometer_tm510r_m2.json"), "--check-only", "--format", "json"])
    assert code == 0
    issues = json.loads(capsys.readouterr().out)
    assert issues[0]["field"] == "specs.Диапазон измерений"


def test_invalid_file(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    bad.write_text("{oops", encoding="utf-8")
    assert main([str(bad)]) == EXIT_INPUT
    assert "Некорректный JSON" in capsys.readouterr().err


def test_missing_file(capsys):
    assert main(["нет_такого.json"]) == EXIT_INPUT
    assert "Файл не найден" in capsys.readouterr().err


def test_missing_key(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main([str(EXAMPLES / "gas_detector_dz1_co.json")]) == EXIT_CONFIG
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
