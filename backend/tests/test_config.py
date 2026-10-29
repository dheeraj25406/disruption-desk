from pathlib import Path

from app.core.config import BACKEND_ENV_FILE, Settings


def test_backend_env_path_is_independent_of_process_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configured_path = Path(Settings.model_config["env_file"])
    assert configured_path == BACKEND_ENV_FILE
    assert configured_path.is_absolute()
    assert configured_path.name == ".env"
