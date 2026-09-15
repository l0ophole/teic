"""Regression test for the terminal-UI hang / `ValueError: bad value(s) in
fds_to_keep` crash.

Root cause: tqdm's `__init__` reaches for `self._lock` even when
`disable=True` (see `tqdm/std.py`'s `if disable: ... with self._lock:`
branch), and that lazily builds a `TqdmDefaultWriteLock`, whose
`create_mp_lock()` calls `multiprocessing.RLock()`. That starts a
`resource_tracker` subprocess which passes `sys.stderr.fileno()` to it.
Textual's `App.run()` redirects `sys.stderr` to `_PrintCapture`, whose
`fileno()` deliberately returns `-1` -- an invalid fd that crashes the
subprocess spawn. So `show_progress_bar=False` alone does not avoid the
crash; `EmbeddingModel._get_model()` must pre-seed tqdm's lock with a
plain `threading.RLock()` via `tqdm.tqdm.set_lock()` *before* any tqdm
bar (disabled or not) gets a chance to construct its own multiprocessing-
backed lock.

Uses a fake `SentenceTransformer` (monkeypatched into the real
`sentence_transformers` module before `EmbeddingModel` imports it) so this
test needs neither the real ~90MB model nor network access.
"""

from __future__ import annotations

from typing import Any

import pytest
import tqdm.std

from teic.memory.embeddings import EmbeddingModel


class FakeSentenceTransformer:
    def __init__(self, model_name: str, device: str) -> None:
        self.model_name = model_name
        self.device = device

    def encode(self, text: str, **kwargs: Any) -> list[float]:
        return [0.0] * 384


def test_get_model_never_builds_a_multiprocessing_tqdm_lock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sentence_transformers

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", FakeSentenceTransformer)
    monkeypatch.delattr(tqdm.std.tqdm, "_lock", raising=False)

    def boom(cls: type) -> None:
        raise AssertionError(
            "tqdm must never reach multiprocessing.RLock() under the TUI -- "
            "it crashes when sys.stderr.fileno() is -1"
        )

    monkeypatch.setattr(tqdm.std.TqdmDefaultWriteLock, "create_mp_lock", classmethod(boom))

    EmbeddingModel()._get_model()

    # Simulates what sentence-transformers' encode() does internally
    # (`trange(..., disable=not show_progress_bar)`): even a *disabled*
    # tqdm bar takes `self._lock` in `__init__`, which is exactly the path
    # that must already be pre-seeded and so never reach create_mp_lock.
    tqdm.std.tqdm(range(1), disable=True)


def test_encode_disables_progress_bar(monkeypatch: pytest.MonkeyPatch) -> None:
    import sentence_transformers

    monkeypatch.setattr(sentence_transformers, "SentenceTransformer", FakeSentenceTransformer)

    calls: list[dict[str, Any]] = []
    original_encode = FakeSentenceTransformer.encode

    def recording_encode(self: FakeSentenceTransformer, text: str, **kwargs: Any) -> list[float]:
        calls.append(kwargs)
        return original_encode(self, text, **kwargs)

    monkeypatch.setattr(FakeSentenceTransformer, "encode", recording_encode)

    EmbeddingModel().encode("hello")

    assert calls == [{"show_progress_bar": False}]
