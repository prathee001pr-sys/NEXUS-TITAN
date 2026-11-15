"""Exercise provider HTTP handling using loopback and a synthetic key only."""
from __future__ import annotations

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread

import pytest

from nexus_titan.self_improvement.llm_provider import (
    LLMConfig, LLMProviderError, OpenAICompatibleProvider,
)


@contextmanager
def local_endpoint(*, redirect_code=None, redirect_target=None):
    observed = []

    class Handler(BaseHTTPRequestHandler):
        def answer(self):
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            observed.append((self.command, bool(self.headers.get("Authorization")), body))
            if redirect_code is not None:
                self.send_response(redirect_code)
                self.send_header("Location", redirect_target)
                payload = b""
            else:
                self.send_response(200)
                payload = json.dumps({"choices": [{"message": {
                    "content": '{"research_only": true}'}}]}).encode()
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        do_POST = answer
        do_GET = answer

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=lambda: server.serve_forever(poll_interval=0.01), daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/v1", observed
    finally:
        server.shutdown()
        thread.join(timeout=2)
        server.server_close()


def provider(url):
    return OpenAICompatibleProvider(LLMConfig(
        base_url=url, model="synthetic-test-model",
        api_key="SYNTHETIC_LOOPBACK_TEST_KEY", timeout_seconds=2,
    ))


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_never_reaches_another_origin(status):
    with local_endpoint() as (sink_url, sink_requests):
        with local_endpoint(redirect_code=status, redirect_target=sink_url) as (url, sent):
            with pytest.raises(LLMProviderError, match="HTTPError"):
                provider(url).complete_json("Synthetic research only", "No secrets")
            assert len(sent) == 1 and sent[0][0] == "POST"
            assert sent[0][1] is True
            assert sink_requests == []


def test_direct_provider_response_still_decodes_json():
    with local_endpoint() as (url, observed):
        result = provider(url).complete_json("Synthetic research only", "No secrets")
        assert result == {"research_only": True}
        assert len(observed) == 1 and observed[0][0] == "POST"
