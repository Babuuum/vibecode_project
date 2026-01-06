import uvicorn

from autocontent.api import main


def test_run_invokes_uvicorn(monkeypatch) -> None:
    captured = {}

    def fake_run(*args, **kwargs):  # noqa: ANN001
        captured["args"] = args
        captured["kwargs"] = kwargs

    monkeypatch.setattr(uvicorn, "run", fake_run)

    main.run()

    assert captured["args"][0] == "autocontent.api.main:app"
    assert captured["kwargs"]["host"] == "0.0.0.0"
    assert captured["kwargs"]["port"] == 8000
