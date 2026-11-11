"""Public source checkouts require a separately supplied participant dataset."""
import subprocess
import sys
import pytest


@pytest.mark.parametrize("kind", ["missing", "empty", "file"])
def test_fresh_clone_reports_missing_kit_before_cloning(tmp_path, kind):
    kit = tmp_path / "participant kit with spaces"
    if kind == "empty":
        kit.mkdir()
    elif kind == "file":
        kit.write_text("not an archive directory", encoding="utf-8")
    result = subprocess.run(
        ["bash", "scripts/fresh_clone_check.sh", "--python", sys.executable,
         "--repo", str(tmp_path / "no repository"), "--snapshots-zip", str(kit)],
        capture_output=True, text=True, timeout=10,
    )
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr.startswith("fresh-clone: FAIL ")
    expected = "no ZIP archives" if kind == "empty" else "snapshot archives are not included"
    assert expected in result.stderr
    assert "git clone" not in result.stderr and "venv" not in result.stderr
