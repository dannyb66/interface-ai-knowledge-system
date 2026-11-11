"""Public source checkouts require a separately supplied participant dataset."""
import subprocess
import sys
import io
from zipfile import ZipFile
import pytest

from scripts.setup_local import ARCHIVES, install_archives


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


def participant_zip(path, *, omit=None, duplicate=None, invalid=None, manifest=True):
    with ZipFile(path, "w") as outer:
        for name in ARCHIVES:
            if name == omit:
                continue
            data = io.BytesIO()
            with ZipFile(data, "w") as inner:
                if manifest:
                    inner.writestr(name[:-4] + "/manifest.json", "{}")
            payload = b"not a zip" if name == invalid else data.getvalue()
            outer.writestr("participant kit/snapshots_zip/" + name, payload)
            if name == duplicate:
                outer.writestr("another kit/snapshots_zip/" + name, payload)


def test_setup_copies_five_archives_and_can_repeat(tmp_path):
    kit = tmp_path / "participant kit.zip"
    destination = tmp_path / "checkout with spaces" / "snapshots_zip"
    participant_zip(kit)
    install_archives(kit, destination)
    before = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in destination.iterdir()}
    assert set(before) == set(ARCHIVES)
    install_archives(kit, destination)
    assert before == {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in destination.iterdir()}


@pytest.mark.parametrize("problem", ["missing", "duplicate", "invalid", "manifest"])
def test_setup_validates_entire_kit_before_writing(tmp_path, problem):
    kit = tmp_path / "participant kit.zip"
    destination = tmp_path / "snapshots_zip"
    options = {
        "missing": {"omit": ARCHIVES[-1]},
        "duplicate": {"duplicate": ARCHIVES[-1]},
        "invalid": {"invalid": ARCHIVES[-1]},
        "manifest": {"manifest": False},
    }
    participant_zip(kit, **options[problem])
    with pytest.raises(ValueError):
        install_archives(kit, destination)
    assert not destination.exists()


def test_setup_does_not_replace_existing_data_or_copy_partial_kit(tmp_path):
    kit = tmp_path / "participant kit.zip"
    destination = tmp_path / "snapshots_zip"
    participant_zip(kit)
    destination.mkdir()
    existing = destination / ARCHIVES[-1]
    existing.write_bytes(b"keep this local archive")
    with pytest.raises(ValueError, match="Existing archive differs; left untouched"):
        install_archives(kit, destination)
    assert list(destination.iterdir()) == [existing]
    assert existing.read_bytes() == b"keep this local archive"
