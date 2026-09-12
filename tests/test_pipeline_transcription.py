from types import SimpleNamespace

from requests.exceptions import ChunkedEncodingError

from minutes.pipeline.transcription import (
    TranscriptionResult,
    transcribe_locally,
    transcribe_remotely,
)


def test_transcribe_locally_reports_segment_and_completion_progress():
    statuses = []
    progress = []

    def transcriber(path, **kwargs):
        assert path == "clean.wav"
        assert kwargs["model_size"] == "small"
        kwargs["progress_callback"](SimpleNamespace(end=5.0))
        return "raw transcript", [{"end": 5.0}]

    result = transcribe_locally(
        "clean.wav",
        duration_seconds=10.0,
        transcriber=transcriber,
        update_status=statuses.append,
        update_progress=progress.append,
    )

    assert result == TranscriptionResult(
        raw_text="raw transcript",
        segments=[{"end": 5.0}],
    )
    assert statuses == ["transcribing:5.0s"]
    assert progress == [50.0, 100.0]


def test_transcribe_locally_skips_percentage_without_duration():
    progress = []

    def transcriber(_path, **kwargs):
        kwargs["progress_callback"](SimpleNamespace(end=2.0))
        return "raw", []

    transcribe_locally(
        "clean.wav",
        duration_seconds=None,
        transcriber=transcriber,
        update_status=lambda _status: None,
        update_progress=progress.append,
    )

    assert progress == [100.0]


class FakeResponse:
    def __init__(self, lines=(), text=""):
        self._lines = lines
        self.text = text
        self.status_code = 200
        self.headers = {}

    def raise_for_status(self):
        return None

    def iter_lines(self, **_kwargs):
        yield from self._lines


def test_transcribe_remotely_parses_streamed_segments(tmp_path):
    audio = tmp_path / "clean.wav"
    audio.write_bytes(b"audio")
    statuses = []
    progress = []
    response = FakeResponse(
        lines=[
            '{"type":"heartbeat"}',
            '{"type":"segment","end":2.5,"text":"hello"}',
            '{"type":"final","raw_text":"hello","segments":[{"end":2.5}]}',
        ]
    )

    result = transcribe_remotely(
        str(audio),
        inference_url="http://inference/transcribe",
        duration_seconds=5.0,
        post=lambda *_args, **_kwargs: response,
        update_status=statuses.append,
        update_progress=progress.append,
    )

    assert result == TranscriptionResult("hello", [{"end": 2.5}])
    assert statuses == ["transcribing:2.5s"]
    assert progress == [50.0, 100.0]


def test_transcribe_remotely_falls_back_after_chunk_error(tmp_path):
    audio = tmp_path / "clean.wav"
    audio.write_bytes(b"audio")
    responses = [
        ChunkedEncodingError("stream ended"),
        FakeResponse(text='{"type":"final","raw_text":"fallback","segments":[]}'),
    ]

    def post(*_args, **_kwargs):
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    result = transcribe_remotely(
        str(audio),
        inference_url="http://inference/transcribe",
        duration_seconds=None,
        post=post,
        update_status=lambda _status: None,
        update_progress=lambda _progress: None,
        sleep=lambda _seconds: None,
    )

    assert result == TranscriptionResult("fallback", [])
    assert responses == []
