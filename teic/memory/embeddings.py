"""Local sentence-embedding wrapper (`PLAN.md`'s approved
`sentence-transformers` dependency).

`device="cpu"` is a **verified constraint, not a style choice**: on this
project's dev machine, constructing `SentenceTransformer` without an
explicit device and calling `.encode()` raises
`torch.AcceleratorError: CUDA error: no kernel image is available for
execution on the device` (a real GPU/driver mismatch, reproduced by hand).
Pinning `device="cpu"` avoids it; embedding a short string is ~1ms on CPU
once the model is loaded, so there is no real cost to not using a GPU here.

Importing this module must not touch disk or network -- the model is
constructed lazily on first `.encode()` call, not at import time, so
callers that only need `decay.py`/`retrieval.py`'s pure math stay fast and
offline-safe.
"""

from __future__ import annotations

MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


class EmbeddingModel:
    def __init__(self) -> None:
        self._model: object | None = None

    def _get_model(self) -> object:
        if self._model is None:
            import threading

            import tqdm
            from sentence_transformers import SentenceTransformer
            from transformers.utils.logging import disable_progress_bar

            # Pre-seeds tqdm's write lock with a plain threading.RLock()
            # *before* any tqdm bar (even a disabled one -- tqdm.__init__
            # takes `self._lock` regardless of `disable`) gets a chance to
            # lazily build its own via TqdmDefaultWriteLock, which reaches
            # for multiprocessing.RLock() and so starts a resource_tracker
            # subprocess. That subprocess spawn passes sys.stderr.fileno();
            # under the terminal UI, Textual has redirected sys.stderr to a
            # file-like whose fileno() deliberately returns -1, which
            # crashes the spawn with "ValueError: bad value(s) in
            # fds_to_keep" and hangs the daemon's tick loop forever. tqdm's
            # own docs endorse set_lock() as the way to hand it a
            # pre-built lock instead of letting it construct one itself.
            tqdm.tqdm.set_lock(threading.RLock())
            # Suppresses huggingface_hub's own tqdm download bars (weight
            # files are already cached, but this covers a cold cache too).
            disable_progress_bar()  # type: ignore[no-untyped-call]
            self._model = SentenceTransformer(MODEL_NAME, device="cpu")
        return self._model

    def encode(self, text: str) -> list[float]:
        model = self._get_model()
        vector = model.encode(text, show_progress_bar=False)  # type: ignore[attr-defined]
        return [float(x) for x in vector]


_default_model: EmbeddingModel | None = None


def get_default_model() -> EmbeddingModel:
    """Lazy process-wide singleton -- avoids reloading the model per call
    site, same "constructed once per session" posture as `SensorArray`."""
    global _default_model
    if _default_model is None:
        _default_model = EmbeddingModel()
    return _default_model
