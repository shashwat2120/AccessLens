from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONTAINER = ROOT / "deploy" / "container"


def test_the_start_script_has_unix_line_endings_and_keeps_the_api_private() -> None:
    script = (CONTAINER / "start.sh").read_bytes()
    assert b"\r" not in script  # bash inside the container fails on Windows line endings
    text = script.decode()
    assert "--host 127.0.0.1 --port 8000" in text  # the API is never public
    assert '--server.port="${PORT:-10000}"' in text  # the host chooses the public port
    assert "token_urlsafe" in text  # a fresh key at every start, never written down
    assert "ACCESSLENS_DISABLE_XSRF" in text  # XSRF protection is on unless a host needs it off


def test_the_dockerfile_runs_as_a_non_root_user_and_pins_its_base_image() -> None:
    dockerfile = (CONTAINER / "Dockerfile").read_text(encoding="utf-8")
    assert "USER 1000:1000" in dockerfile
    assert "@sha256:" in dockerfile
    assert "APP_ENV=prod" in dockerfile
    assert "KEY" not in dockerfile.replace("API_KEYS", "")  # no secrets baked into the image
    for path in ("deploy/container/start.sh", "ui", ".streamlit", "src"):
        assert (ROOT / path).exists(), path  # every COPY source exists in the repo


def test_the_render_blueprint_uses_the_free_plan_and_keeps_keys_out_of_the_repo() -> None:
    blueprint = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "plan: free" in blueprint
    assert "dockerfilePath: ./deploy/container/Dockerfile" in blueprint
    assert "healthCheckPath: /_stcore/health" in blueprint
    for secret in ("GEMINI_API_KEY", "GROQ_API_KEY"):
        after = blueprint.split(f"key: {secret}")[1].splitlines()[1]
        assert after.strip() == "sync: false"  # asked for at creation, never stored here
