import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "huggingface" / "build_space.py"


def load_builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_space", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_space_folder_has_everything_the_image_needs_and_no_secrets(tmp_path: Path) -> None:
    out = load_builder().build(tmp_path / "space")
    for name in ("Dockerfile", "start.sh", "README.md", "pyproject.toml", "uv.lock", "LICENSE"):
        assert (out / name).is_file(), name
    assert (out / "src" / "accesslens" / "service.py").is_file()
    assert (out / "ui" / "streamlit_app.py").is_file()
    assert (out / "ui" / "samples" / "sample-team-update.pptx").is_file()
    assert (out / ".streamlit" / "config.toml").is_file()
    names = {p.name for p in out.rglob("*")}
    assert not names & {".env", "__pycache__"}
    assert not any(n.startswith(".env.") for n in names)


def test_the_start_script_has_unix_line_endings_and_keeps_the_api_private(
    tmp_path: Path,
) -> None:
    out = load_builder().build(tmp_path / "space")
    script = (out / "start.sh").read_bytes()
    assert b"\r" not in script  # bash inside the container fails on Windows line endings
    text = script.decode()
    assert "--host 127.0.0.1 --port 8000" in text  # the API is never public
    assert "--server.port=7860" in text
    assert "token_urlsafe" in text  # a fresh key at every start, never written down


def test_the_space_card_declares_a_docker_space_on_the_ui_port() -> None:
    card = (ROOT / "deploy" / "huggingface" / "README.md").read_text(encoding="utf-8")
    header = card.split("---")[1]
    assert "sdk: docker" in header and "app_port: 7860" in header


def test_the_dockerfile_runs_as_a_non_root_user_and_pins_its_base_image() -> None:
    dockerfile = (ROOT / "deploy" / "huggingface" / "Dockerfile").read_text(encoding="utf-8")
    assert "USER 1000:1000" in dockerfile
    assert "@sha256:" in dockerfile
    assert "APP_ENV=prod" in dockerfile
    assert "KEY" not in dockerfile.replace("API_KEYS", "")  # no secrets baked into the image
