"""A request is sent on only when the gateway can read what its checks look at; ordinary requests, uploads and reads
work as before."""

import gzip
import json
import os
import time
import unittest

from gateway.config import Provider
from tests.support import Rig

ALLOWED, OTHER = "claude-haiku-4-5", "claude-opus-5-5"
SECRET = "AKIAIOSFODNN7EXAMPLE"
JSON = "application/json"
UPLOAD = "multipart/form-data; boundary=b"
FORM = b'--b\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n\r\nRIFF\r\n--b--\r\n'
MODEL_PATHS = ("/anthropic/v1/messages", "/anthropic/v1/messages/count_tokens", "/openai/v1/responses",
               "/openai/v1/responses/compact", "/openai/v1/chat/completions", "/openai/v1/completions",
               "/openai/v1/embeddings")
MEDIA_PATHS = ("/higgsfield/flux-pro/image", "/elevenlabs/v1/text-to-speech/v1")


def text(model=OTHER, more=""):
    words = f"hello {SECRET}"
    return (f'{{"model": "{model}", "max_tokens": 20, "prompt": "{words}", "input": "{words}",'
            f' "messages": [{{"role": "user", "content": "{words}"}}]{more}}}').encode()


# (what is sent, its headers, status, the reason recorded)
UNREAD = (
    (text(more=', "extra": ' + "9" * 5000), {"content-type": JSON}, 400, "body not readable"),
    (b" " + text(), {"content-type": "text/plain"}, 415, "body type not accepted"),
    (gzip.compress(text()), {"content-type": JSON, "content-encoding": "gzip"}, 415, "body encoding not accepted"),
    (text(), {"content-type": JSON, "content-encoding": "br"}, 415, "body encoding not accepted"),
    (text(), {"content-type": JSON, "Content-Encoding": "identity, zstd"}, 415, "body encoding not accepted"),
    (text(), {"content-type": JSON, "content-encoding": "identity", "Content-Encoding": "gzip"}, 415,
     "body encoding not accepted"),
    (text(), {"content-type": "text/plain"}, 415, "body type not accepted"),
    (text(), {"content-type": "application/x-www-form-urlencoded"}, 415, "body type not accepted"),
    (text(), {"content-type": JSON + "; charset=utf-16"}, 415, "body type not accepted"),
    (text(), {"content-type": JSON, "Content-Type": "text/plain"}, 415, "body type not accepted"),
    (text(), {}, 415, "body type not accepted"),
    (b"\xef\xbb\xbf" + text(), {"content-type": JSON}, 400, "body not readable"),
    (text().decode().encode("utf-16"), {"content-type": JSON}, 400, "body not readable"),
    (text() + b"}", {"content-type": JSON}, 400, "body not readable"),
    (b"[" + text() + b"]", {"content-type": JSON}, 400, "body not readable"),
    (text(more=f', "model": "{ALLOWED}"'), {"content-type": JSON}, 400, "body not readable"),
    (text(more=', "extra": {"a": 1, "a": 2}'), {"content-type": JSON}, 400, "body not readable"),
)


class FormCase(unittest.TestCase):
    def setUp(self):
        self.rig = Rig()
        self.addCleanup(self.rig.close)
        self.db = self.rig.gw.db
        os.environ["FAKE_CUSTOM_KEY"] = "custom-provider-secret"
        self.rig.settings.providers["custom"] = Provider("custom", self.rig.fake.url, "FAKE_CUSTOM_KEY", "media", label="Custom")

    def send(self, path, body, headers, method="POST"):
        """-> (status, body, the request's record, how many requests reached the provider)"""
        sent, before = len(self.rig.fake.seen), self.db.scalar("SELECT COUNT(*) FROM requests")
        headers = {"authorization": f"Bearer {self.rig.key}", "user-agent": "python-requests/2.32", **headers}
        # the helper adds a JSON Content-Type of its own unless one is named, so write the request by hand
        status, payload = self.raw(method, path, body, headers)
        self.rig.wait_for(lambda: self.db.scalar("SELECT COUNT(*) FROM requests") > before)
        return status, payload, self.rig.last_record(), len(self.rig.fake.seen) - sent

    def raw(self, method, path, body, headers):
        import http.client

        conn = http.client.HTTPConnection("127.0.0.1", self.rig.port, timeout=30)
        try:
            conn.putrequest(method, path, skip_accept_encoding=True)
            for name, value in headers.items():
                conn.putheader(name, value)
            if body is not None:
                conn.putheader("Content-Length", str(len(body)))
            conn.endheaders(body)
            resp = conn.getresponse()
            return resp.status, resp.read()
        finally:
            conn.close()

    def refused(self, path, body, headers, status, reason):
        got, payload, row, reached = self.send(path, body, headers)
        self.assertEqual((got, row["status"], row["outcome"], row["reason"], reached),
                         (status, status, "blocked", reason, 0), payload)
        self.assertEqual((row["person_id"], row["key_id"], row["req_head"]), (self.rig.person_id, self.rig.key_id, None))

    def passed(self, path, body, headers, method="POST"):
        """The request reached the provider (the stand-in answers 404 for a path it doesn't play)."""
        status, payload, row, reached = self.send(path, body, headers, method)
        self.assertEqual((reached, row["outcome"] != "blocked"), (1, True), (status, row["reason"], payload))
        return status, row


class UnreadRequestTests(FormCase):
    def sweep(self, cases=UNREAD[:3]):
        for path in MODEL_PATHS + MEDIA_PATHS:
            for i, (body, headers, status, reason) in enumerate(cases):
                with self.subTest(path=path, case=i):
                    self.refused(path, body, headers, status, reason)

    def never_sent(self):
        """Every case is refused, here or by an earlier rule that could already read the model."""
        for path in MODEL_PATHS:
            for i, (body, headers, _, _) in enumerate(UNREAD):
                with self.subTest(path=path, case=i):
                    status, _, row, reached = self.send(path, body, headers)
                    self.assertEqual((status in (400, 403, 415), row["outcome"], reached), (True, "blocked", 0),
                                     (status, row["reason"]))

    def test_with_a_persons_model_list(self):
        self.db.x("UPDATE people SET allowed_models = 'claude-haiku-*' WHERE id = ?", (self.rig.person_id,))
        self.sweep()
        self.never_sent()
        status, _, row, reached = self.send(MODEL_PATHS[0], text(), {"content-type": JSON})
        self.assertEqual((status, row["reason"], reached), (403, "model not allowed", 0))
        self.passed(MODEL_PATHS[0], text(ALLOWED), {"content-type": JSON})

    def test_with_a_model_switched_off(self):
        self.db.x("INSERT OR REPLACE INTO models(id, provider, label, status, updated) VALUES(?, 'anthropic', ?, 'disabled', ?)",
                  (OTHER, OTHER, time.time()))
        self.sweep()
        status, _, row, reached = self.send(MODEL_PATHS[0], text(), {"content-type": JSON})
        self.assertEqual((status, row["reason"], reached), (403, "model disabled", 0))
        self.passed(MODEL_PATHS[0], text(ALLOWED), {"content-type": JSON})

    def test_with_credential_blocking_on(self):
        self.db.set_setting("block_secrets", "1")
        self.sweep(UNREAD)
        for path in (MODEL_PATHS[0], MODEL_PATHS[2], MODEL_PATHS[4], *MEDIA_PATHS):
            with self.subTest(path=path):
                status, _, row, reached = self.send(path, text(), {"content-type": JSON})
                self.assertEqual((status, row["reason"], reached), (403, "secret in prompt", 0))

    def test_a_model_has_to_be_named(self):
        for model in (None, '""', "5", "null", '["a"]', '{"id": "a"}', '"a b"', '"a\\n"', '"' + "a" * 201 + '"'):
            body = b'{"input": "x"}' if model is None else f'{{"input": "x", "model": {model}}}'.encode()
            for path in MODEL_PATHS:
                with self.subTest(path=path, model=model):
                    self.refused(path, body, {"content-type": JSON}, 400, "no readable model")
        for path in MODEL_PATHS:
            for body, headers in ((b"", {"content-type": JSON}), (None, {})):
                with self.subTest(path=path, body=body):
                    status = 415 if not headers else 400
                    got, _, row, reached = self.send(path, body, headers)
                    self.assertEqual((got, row["outcome"], reached), (status, "blocked", 0), row["reason"])

    def test_a_form_upload_is_not_a_model_request(self):
        for path in MODEL_PATHS + MEDIA_PATHS:
            with self.subTest(path=path):
                self.refused(path, FORM, {"content-type": UPLOAD}, 415, "body type not accepted")

    def test_an_unexpected_item_type_is_recorded(self):
        for kind in (5, None, ["a"]):
            body = json.dumps({"model": "gpt-6.1", "input": [{"type": kind, "content": "x"}]}).encode()
            with self.subTest(kind=kind):
                status, row = self.passed("/openai/v1/responses", body, {"content-type": JSON})
                self.assertEqual((status, row["person_id"]), (200, self.rig.person_id))

    def test_unexpected_stream_options_are_the_providers_to_judge(self):
        for options in (5, "x", [1], True):
            body = json.dumps({"model": "gpt-6.1", "stream": True, "stream_options": options,
                               "messages": [{"role": "user", "content": "hi"}]}).encode()
            with self.subTest(options=options):
                self.passed("/openai/v1/chat/completions", body, {"content-type": JSON})
                self.assertEqual(self.rig.fake.seen[-1]["body"]["stream_options"], options)


class OrdinaryRequestTests(FormCase):
    def test_model_requests(self):
        self.db.x("UPDATE people SET allowed_models = 'claude-haiku-*' WHERE id = ?", (self.rig.person_id,))
        for ctype in (JSON, "application/json; charset=utf-8", "Application/JSON;charset=UTF-8"):
            for encoding in ({}, {"content-encoding": "identity"}):
                for path in MODEL_PATHS:
                    with self.subTest(path=path, ctype=ctype, encoding=encoding):
                        self.passed(path, text(ALLOWED), {"content-type": ctype, **encoding})
        for model in ("claude-haiku-4-5[1m]", "claude-haiku-4-5@20260101"):
            self.passed(MODEL_PATHS[0], text(model), {"content-type": JSON})

    def test_uploads(self):
        for path in ("/elevenlabs/v1/speech-to-text", "/elevenlabs/v1/speech-to-speech/v1",
                     "/elevenlabs/v1/speech-to-speech/v1/stream", "/elevenlabs/v1/music/upload"):
            with self.subTest(path=path):
                self.passed(path, FORM, {"content-type": UPLOAD})
        # one an admin added takes files too, on either kind of provider
        self.rig.gw.extra_endpoints = "POST /v1/audio/*"
        for path in ("/openai/v1/audio/transcriptions", "/elevenlabs/v1/audio/isolation"):
            with self.subTest(path=path):
                self.passed(path, FORM, {"content-type": UPLOAD})
        self.refused("/openai/v1/audio/speech", text(), {"content-type": "text/plain"}, 415, "body type not accepted")
        self.passed("/openai/v1/audio/speech", b'{"input": "x"}', {"content-type": JSON})

    def test_media_requests_reads_and_empty_bodies(self):
        for path in MEDIA_PATHS:
            self.passed(path, b'{"text": "hello", "prompt": "hello"}', {"content-type": JSON})
        for path in ("/anthropic/v1/models", "/openai/v1/models/gpt-6.1", "/elevenlabs/v1/voices", "/higgsfield/v1/motions"):
            with self.subTest(path=path):
                self.passed(path, None, {}, method="GET")
        status, _, row, _ = self.send(MEDIA_PATHS[0], b'{"prompt": "p"}', {"content-type": JSON})
        job = row["turn_id"]
        for body in (None, b""):
            with self.subTest(body=body):
                self.passed(f"/higgsfield/requests/{job}/cancel", body, {})


if __name__ == "__main__":
    unittest.main()
