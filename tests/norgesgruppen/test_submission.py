"""Tests for packaged Norgesgruppen submissions."""

from __future__ import annotations

import json
import os
import subprocess
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SUBMISSIONS_DIR = REPO_ROOT / "norgesgruppen" / "submissions"
MODEL_FILES = {"best.pt", "model.onnx"}


def iter_timestamped_submission_roots() -> list[Path]:
    """Return timestamped submission directories matching the packaging convention."""
    if not SUBMISSIONS_DIR.exists():
        return []
    return sorted(
        path
        for path in SUBMISSIONS_DIR.iterdir()
        if path.is_dir()
        and len(path.name) == 15
        and path.name[8] == "_"
        and path.name.replace("_", "").isdigit()
    )


def create_stub_runtime(stubs_dir: Path) -> None:
    """Create stub runtime modules for CLI execution."""
    stubs_dir.mkdir(parents=True, exist_ok=True)
    (stubs_dir / "ultralytics").mkdir(parents=True, exist_ok=True)
    (stubs_dir / "torch.py").write_text(
        """
class _NoGrad:
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc, tb):
        return False


def no_grad():
    return _NoGrad()
""".strip() + "\n",
    )
    (stubs_dir / "ultralytics" / "__init__.py").write_text(
        """
class _FakeArray:
    def __init__(self, values):
        self._values = values

    def cpu(self):
        return self

    def numpy(self):
        return self._values


class _FakeScalar:
    def __init__(self, value):
        self._value = value

    def cpu(self):
        return self

    def item(self):
        return self._value


class _FakeTensorList:
    def __init__(self, values):
        self._values = values

    def __getitem__(self, index):
        return self._values[index]

    def __len__(self):
        return len(self._values)


class _FakeBoxes:
    def __init__(self):
        self.xyxy = _FakeTensorList([_FakeArray([10.0, 20.0, 50.0, 80.0])])
        self.cls = _FakeTensorList([_FakeScalar(123)])
        self.conf = _FakeTensorList([_FakeScalar(0.95)])

    def __len__(self):
        return 1


class _FakeResult:
    def __init__(self):
        self.boxes = _FakeBoxes()


class YOLO:
    def __init__(self, weights_path):
        self.weights_path = weights_path

    def fuse(self):
        return None

    def predict(self, **kwargs):
        return [_FakeResult()]
""".strip() + "\n",
    )
    (stubs_dir / "onnxruntime.py").write_text(
        """
import numpy as np


class _FakeInput:
    name = "images"


class _FakeOutput:
    name = "output0"


class InferenceSession:
    def __init__(self, weights_path, providers=None):
        self.weights_path = weights_path
        self.providers = providers or []

    def get_inputs(self):
        return [_FakeInput()]

    def get_outputs(self):
        return [_FakeOutput()]

    def run(self, output_names, inputs):
        predictions = np.zeros((1, 128, 1), dtype=np.float32)
        predictions[0, 0:4, 0] = np.array([384.0, 640.0, 512.0, 768.0], dtype=np.float32)
        predictions[0, 4 + 123, 0] = 0.95
        return [predictions]
""".strip() + "\n",
    )


def run_submission_cli(
    run_py_path: Path,
    images_dir: Path,
    output_path: Path,
    stubs_dir: Path,
) -> None:
    """Run the packaged submission through its CLI with stubbed dependencies."""
    env = os.environ.copy()
    pythonpath_parts = [str(stubs_dir)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    subprocess.run(  # noqa: S603
        [
            "uv",
            "run",
            "python",
            str(run_py_path),
            "--input",
            str(images_dir),
            "--output",
            str(output_path),
        ],
        check=True,
        cwd=REPO_ROOT,
        env=env,
    )


def assert_predictions_schema(payload: object) -> None:
    """Validate the packaged inference output schema."""
    assert isinstance(payload, list)
    assert payload

    for prediction in payload:
        assert isinstance(prediction, dict)
        assert set(prediction) == {"image_id", "bbox", "category_id", "score"}
        assert isinstance(prediction["image_id"], int)
        assert prediction["image_id"] >= 0
        assert isinstance(prediction["bbox"], list)
        assert len(prediction["bbox"]) == 4
        assert all(isinstance(value, float) for value in prediction["bbox"])
        assert all(value >= 0.0 for value in prediction["bbox"])
        assert isinstance(prediction["category_id"], int)
        assert prediction["category_id"] >= 0
        assert isinstance(prediction["score"], float)
        assert prediction["score"] >= 0.0
        assert prediction["score"] <= 1.0


def test_every_submission_supports_inference_and_expected_layout(tmp_path: Path) -> None:
    """Verify every packaged submission is minimal, consistent, and runnable."""
    submission_roots = iter_timestamped_submission_roots()
    assert submission_roots, "No timestamped submissions found in norgesgruppen/submissions"

    for index, submission_root in enumerate(submission_roots):
        submission_dir = submission_root / "submission"
        submission_zip = submission_root / "submission.zip"

        assert submission_dir.is_dir(), f"Missing submission dir in {submission_root}"
        assert submission_zip.is_file(), f"Missing submission zip in {submission_root}"

        dir_files = {path.name for path in submission_dir.iterdir() if path.is_file()}
        assert "run.py" in dir_files
        model_files = dir_files & MODEL_FILES
        assert len(model_files) == 1
        assert dir_files == {"run.py", *model_files}

        for file_name in dir_files:
            file_path = submission_dir / file_name
            assert file_path.stat().st_size > 0

        with zipfile.ZipFile(submission_zip) as zf:
            zip_names = set(zf.namelist())
            assert zip_names == dir_files
            # for name in dir_files:
            # zip_info = zf.getinfo(name)
            # assert zip_info.file_size == (submission_dir / name).stat().st_size

        images_dir = tmp_path / f"images_{index}"
        images_dir.mkdir()
        (images_dir / "img_00001.jpg").write_bytes(b"fake-image")
        output_path = tmp_path / f"output_{index}.json"
        stubs_dir = tmp_path / f"stubs_{index}"
        create_stub_runtime(stubs_dir)

        run_submission_cli(submission_dir / "run.py", images_dir, output_path, stubs_dir)

        assert output_path.is_file()
        payload = json.loads(output_path.read_text())
        assert_predictions_schema(payload)
