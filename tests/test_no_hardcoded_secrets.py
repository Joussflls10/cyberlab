from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__"}


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        yield path


def test_no_hardcoded_openrouter_keys_in_python_files():
    secret_prefix = "sk-or-v1" + "-"
    offenders = []

    for file_path in _iter_python_files(ROOT):
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if secret_prefix in line:
                offenders.append(f"{file_path.relative_to(ROOT)}:{line_no}")

    assert not offenders, (
        "Found hardcoded OpenRouter-style key material in Python files:\n"
        + "\n".join(offenders)
    )