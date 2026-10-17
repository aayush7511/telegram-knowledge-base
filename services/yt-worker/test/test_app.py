"""POST /transcript — the home worker's side of specs/youtube-home-worker.md.

youtube-transcript-api is replaced by a fake (app.get_api) whose list() returns
fake transcripts or raises the library's real exceptions — offline.
"""
import pytest
import youtube_transcript_api as yta
from fastapi.testclient import TestClient
from youtube_transcript_api import FetchedTranscript, FetchedTranscriptSnippet

import app

SECRET = "yt-secret"
VID = "zjkBMFhNj_g"


class FakeTranscript:
    def __init__(self, language_code, is_generated, text="hello world"):
        self.language_code, self.is_generated, self.text = language_code, is_generated, text
        self.language = language_code

    def fetch(self):
        return FetchedTranscript(
            snippets=[FetchedTranscriptSnippet(text=w, start=i, duration=1.0) for i, w in enumerate(self.text.split())],
            video_id=VID, language=self.language, language_code=self.language_code, is_generated=self.is_generated,
        )


class FakeApi:
    def __init__(self, result):
        self.result, self.calls = result, []

    def list(self, video_id):
        self.calls.append(video_id)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def _client(monkeypatch, result):
    monkeypatch.setenv("YT_WORKER_SECRET", SECRET)
    api = FakeApi(result)
    monkeypatch.setattr(app, "get_api", lambda: api)
    return TestClient(app.app), api


def _post(client, secret=SECRET, video_id=VID):
    headers = {} if secret is None else {"X-KB-Secret": secret}
    return client.post("/transcript", headers=headers, json={"video_id": video_id})


# --- 1, 2: English captions, human-written or auto-generated -----------------

@pytest.mark.parametrize("is_generated", [False, True])
def test_english_captions(monkeypatch, is_generated):
    client, api = _client(monkeypatch, [FakeTranscript("en", is_generated, "hi everyone so recently")])
    resp = _post(client)
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "text": "hi everyone so recently", "language": "en", "is_generated": is_generated}
    assert api.calls == [VID]


def test_regional_english_counts(monkeypatch):
    client, _ = _client(monkeypatch, [FakeTranscript("en-GB", False, "cheers")])
    assert _post(client).json()["status"] == "ok"


def test_english_found_among_other_languages(monkeypatch):
    client, _ = _client(monkeypatch, [FakeTranscript("de", False, "hallo"), FakeTranscript("en", True, "hello")])
    assert _post(client).json()["text"] == "hello"


# --- 3, 4: no captions, or none in English ----------------------------------

@pytest.mark.parametrize("result", [
    yta.TranscriptsDisabled(VID),
    [],
    [FakeTranscript("es", False, "hola"), FakeTranscript("fr", True, "bonjour")],
], ids=["disabled", "empty", "other-languages-only"])
def test_no_english_captions(monkeypatch, result):
    client, _ = _client(monkeypatch, result)
    resp = _post(client)
    assert resp.status_code == 200
    assert resp.json() == {"status": "no_captions"}


# --- 5: blocked -------------------------------------------------------------

@pytest.mark.parametrize("exc", [yta.RequestBlocked(VID), yta.IpBlocked(VID)], ids=["request-blocked", "ip-blocked"])
def test_blocked(monkeypatch, exc):
    client, _ = _client(monkeypatch, exc)
    resp = _post(client)
    assert resp.status_code == 200
    assert resp.json() == {"status": "blocked"}


# --- 6: private / deleted / doesn't exist -----------------------------------

@pytest.mark.parametrize("exc", [
    yta.VideoUnavailable(VID),
    yta.VideoUnplayable(VID, "Private video", []),
    yta.InvalidVideoId(VID),
], ids=["unavailable", "unplayable", "invalid-id"])
def test_unavailable(monkeypatch, exc):
    client, _ = _client(monkeypatch, exc)
    resp = _post(client)
    assert resp.status_code == 200
    assert resp.json() == {"status": "unavailable"}


# --- 7: the secret ----------------------------------------------------------

@pytest.mark.parametrize("secret", ["wrong", None, "x-kb-secret-value"], ids=["wrong", "missing", "other-service-secret"])
def test_bad_secret_is_401_and_fetches_nothing(monkeypatch, secret):
    client, api = _client(monkeypatch, [FakeTranscript("en", False)])
    resp = _post(client, secret=secret)
    assert resp.status_code == 401
    assert api.calls == []


def test_unset_secret_rejects_everything(monkeypatch):
    client, api = _client(monkeypatch, [FakeTranscript("en", False)])
    monkeypatch.delenv("YT_WORKER_SECRET")
    assert _post(client, secret="").status_code == 401
    assert api.calls == []
