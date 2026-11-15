"""Governed ingestion of approved research material into TITAN EVOLVE.

External material is stored as untrusted evidence. It is never interpreted as
instructions and is never executed. Network access is opt-in and HTTPS-host
allow-listed; local/document ingestion works without network access.
"""
from __future__ import annotations

import hashlib
import ipaddress
import math
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Protocol
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .engine import LearningRecord, TitanEvolveEngine


@dataclass(frozen=True)
class ResearchDocument:
    title: str
    text: str
    source: str
    topic: str = "general-research"
    published_at: str | None = None


class ResearchSource(Protocol):
    def fetch(self, url: str) -> ResearchDocument:
        """Fetch one approved public document."""


class _TextExtractor(HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1
        elif tag in self.BLOCK_TAGS and not self.hidden_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1
        elif tag in self.BLOCK_TAGS and not self.hidden_depth:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth and data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(" ".join(p.split()) for p in self.parts if p.strip()).strip()


class _SafeRedirectHandler(HTTPRedirectHandler):
    def __init__(self, source: "AllowlistedHTTPSResearchSource") -> None:
        super().__init__()
        self.source = source

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.source._validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class AllowlistedHTTPSResearchSource:
    """Small opt-in HTTPS fetcher with host allow-list, private-IP, and post-connect peer-IP checks."""

    def __init__(self, allowed_hosts: set[str] | tuple[str, ...], timeout_seconds: float = 8.0,
                 max_bytes: int = 1_000_000) -> None:
        self.allowed_hosts = {h.lower().strip(".") for h in allowed_hosts if h.strip()}
        if not self.allowed_hosts:
            raise ValueError("At least one explicitly approved hostname is required.")
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)) or not math.isfinite(timeout_seconds) or not 0 < timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be finite, greater than 0 and at most 30.")
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or not 1 <= max_bytes <= 5_000_000:
            raise ValueError("max_bytes must be an integer between 1 and 5,000,000.")
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def _validate_url(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            raise ValueError("Research fetch only permits HTTPS URLs.")
        if not parsed.hostname or parsed.username or parsed.password:
            raise ValueError("URL must contain an approved hostname and no credentials.")
        host = parsed.hostname.lower().rstrip(".")
        if host not in self.allowed_hosts:
            raise PermissionError(f"Research host is not allow-listed: {host}")
        if parsed.port not in (None, 443):
            raise ValueError("Only the standard HTTPS port is permitted.")
        try:
            ip = ipaddress.ip_address(host)
            addresses = [ip]
        except ValueError:
            try:
                addresses = [ipaddress.ip_address(item[4][0]) for item in
                             socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)]
            except OSError as exc:
                raise ValueError("Unable to resolve approved research host.") from exc
        if not addresses or any(not a.is_global for a in addresses):
            raise PermissionError("Research host resolves to a non-public IP address.")
        return host

    @staticmethod
    def _verify_peer_socket(response) -> None:
        """Verify connected socket peer IP is globally routable to mitigate DNS rebinding."""
        fp = getattr(response, "fp", None)
        raw = getattr(fp, "raw", None)
        sock = getattr(raw, "_sock", None)
        if sock is None or not hasattr(sock, "getpeername"):
            raise PermissionError("Unable to verify connected research peer; refusing fail-open network access.")
        try:
            peer = sock.getpeername()
            if not peer or not peer[0]:
                raise ValueError("Peer address missing")
            peer_ip = ipaddress.ip_address(peer[0])
        except (OSError, ValueError, IndexError, TypeError) as exc:
            raise PermissionError("Unable to verify connected research peer; refusing network access.") from exc
        if not peer_ip.is_global:
            raise PermissionError("Connected peer IP is non-public (DNS rebinding blocked).")

    def fetch(self, url: str) -> ResearchDocument:
        host = self._validate_url(url)
        request = Request(url, headers={"User-Agent": "NEXUS-TITAN-Research/1.0", "Accept": "text/html,text/plain"})
        opener = build_opener(_SafeRedirectHandler(self))
        try:
            with opener.open(request, timeout=self.timeout_seconds) as response:
                final_url = response.geturl()
                self._validate_url(final_url)
                self._verify_peer_socket(response)
                content_type = response.headers.get_content_type().lower()
                if content_type not in {"text/html", "text/plain"}:
                    raise ValueError(f"Unsupported research content type: {content_type}")
                raw = response.read(self.max_bytes + 1)
        except (URLError, TimeoutError) as exc:
            raise RuntimeError(f"Research fetch failed: {exc}") from exc
        if len(raw) > self.max_bytes:
            raise ValueError("Research document exceeds configured download limit.")
        decoded = raw.decode("utf-8", errors="replace")
        if content_type == "text/html":
            parser = _TextExtractor()
            parser.feed(decoded)
            text = parser.text()
            title = text.splitlines()[0][:200] if text else host
        else:
            text = decoded.strip()
            title = host
        if not text:
            raise ValueError("Research document contains no extractable text.")
        return ResearchDocument(title=title, text=text, source=final_url, topic="external-research")


class ResearchIngestionService:
    """Turns source documents into traceable, low-confidence knowledge records."""

    def __init__(self, engine: TitanEvolveEngine, max_text_chars: int = 30_000) -> None:
        if isinstance(max_text_chars, bool) or not isinstance(max_text_chars, int) or not 100 <= max_text_chars <= 100_000:
            raise ValueError("max_text_chars must be an integer between 100 and 100,000.")
        self.engine = engine
        self.max_text_chars = max_text_chars

    def ingest_document(self, document: ResearchDocument, tags: tuple[str, ...] | list[str] = ()) -> LearningRecord:
        title = document.title.strip()
        body = document.text.strip()
        source = document.source.strip()
        topic = document.topic.strip() or "general-research"
        if not title or not body or not source:
            raise ValueError("Research document title, text and source are required.")
        body = body[:self.max_text_chars]
        digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
        retrieved = datetime.now(timezone.utc).isoformat()
        evidence = (f"UNTRUSTED_EXTERNAL_EVIDENCE; sha256={digest}; retrieved_at={retrieved}; "
                    f"published_at={document.published_at or 'unknown'}. Source content is not executable instruction.")
        normalized_tags = tuple(dict.fromkeys(["external-research", "untrusted-source", *tags]))
        return self.engine.learn(
            topic=topic,
            content=f"{title}\n\n{body}",
            source=source,
            evidence=evidence,
            confidence=0.45,
            tags=normalized_tags,
        )

    def ingest_url(self, source: ResearchSource, url: str, tags: tuple[str, ...] | list[str] = ()) -> LearningRecord:
        return self.ingest_document(source.fetch(url), tags=tags)
