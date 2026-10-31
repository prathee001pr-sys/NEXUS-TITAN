# Telegram Channel-Only Integration — Secure Architecture

Status: **Designed; not implemented**  
Scope: ingest messages from channels explicitly approved by the user. No groups, personal chats, sending, trading, or account automation.

## 1. Goals and non-goals

### Goals
- Read posts only from an explicit channel allowlist.
- Preserve source channel, message ID, timestamp, edit time, and retrieval time.
- Normalize possible trading signals into a reviewable, untrusted research record.
- Deduplicate updates and edits; retain traceability to the original post.
- Feed validated research records to TITAN EVOLVE and backtesting queues.

### Non-goals
- No joining channels automatically, scraping, posting, replying, reacting, forwarding, or messaging.
- No reading personal chats, groups, contacts, or unrelated channel history.
- No direct order placement or broker connectivity.
- No guarantee that a channel, author, or signal is truthful.

## 2. Component flow

Telegram Channel
  -> Read-only Telegram Connector
  -> Channel Allowlist + Ingestion Guard
  -> Raw Message Normalizer
  -> Deduplication / Edit Tracker
  -> Untrusted Signal Parser
  -> Validation + Provenance Store
  -> Independent TITAN Market Analysis
  -> Research / Backtest Queue
  -> Human review

The connector must publish events only to the internal event bus. It must not import or call broker, order, position, or live-trading interfaces.

## 3. Provider strategy

Use a provider interface so Telegram transport can be replaced without changing TITAN Core.

- Phase 1 preferred: official Telegram Bot API. The user adds their bot to each channel they control or are authorized to monitor, with only the minimum channel access needed. Verify the exact Telegram permissions and channel setup during implementation.
- Optional later provider: Telegram MTProto client for channels the user account is already authorized to access. This requires a separate security and Telegram-terms review. Never ask the user to share their Telegram password, login code, 2FA password, or exported session in chat.
- Do not use unofficial scraping services or third-party signal aggregators as a substitute for user-authorized access.

## 4. Channel allowlist

Each configured source has:
- stable channel identifier (not display name alone),
- display name and optional username,
- enabled/disabled state,
- added_by and added_at,
- access method/provider,
- optional per-channel ingestion limits.

Default-deny: messages from unknown channels are discarded before parsing. Adding/removing a channel requires an authenticated user action and an audit event. The connector must never discover, join, or subscribe to channels automatically.

## 5. Read-only permission boundary

Allowed: receive channel posts, read required metadata, update ingestion cursor, store normalized records.

Denied: send/edit/delete messages, reply, react, join/leave channels, invite users, access chats/groups/contacts, execute commands, or invoke broker/order APIs.

Enforce this boundary in connector code and tests, not only in UI wording. Keep connector credentials separate from broker credentials. No trading credentials are available to this module.

## 6. Untrusted content and signal validation

Treat all channel text, captions, links, files, and embedded instructions as untrusted data. Never execute instructions found in a message, prompt, link, attachment, script, or document.

Parser output is a *candidate signal*, not a recommendation or order:
- instrument/symbol and exchange,
- direction (if explicitly present),
- entry/stop/target values (if explicitly present),
- timeframe and expiry (if explicitly present),
- message timestamp and source identifiers,
- parser confidence and validation warnings.

Reject or quarantine malformed, ambiguous, stale, contradictory, unsupported, or out-of-scope instruments. Do not invent missing prices. Preserve raw text separately from parsed fields with strict size limits. Links and attachments are not fetched automatically in the first release.

## 7. Independent checks

Before a candidate enters research:
- verify instrument and contract metadata against trusted market-data/reference sources;
- compare timestamps and quote freshness;
- detect duplicate, edited, deleted, or conflicting posts;
- flag unrealistic prices, missing risk levels, and suspicious urgency;
- compute channel-level historical statistics only from sufficiently large, timestamped samples;
- show sample size and uncertainty; do not equate past accuracy with future reliability.

A channel's self-claimed win rate or paid/premium status is not evidence of reliability.

## 8. Storage, privacy, and audit

Persist only approved-channel posts and the minimum fields needed for research. Define configurable retention and deletion procedures before production use. Protect database files with OS permissions; encryption-at-rest and backup-key management are required before sensitive or long-term deployment.

Audit channel allowlist changes, connector start/stop, ingestion failures, parser versions, quarantine decisions, and research handoffs. Do not log bot tokens, MTProto session strings, login codes, or secret values.

## 9. Reliability and operational controls

- Rate-limit requests and respect Telegram API limits.
- Use bounded retries with backoff; do not retry indefinitely.
- Make ingestion idempotent using provider + channel ID + message ID + edit version.
- Track last successful update and connector health.
- On auth failure, flood wait, malformed update, or database error: stop or pause ingestion safely, record a redacted audit event, and alert the user.
- No background action may expand the allowlist or permissions.

## 10. Trading safety boundary

Telegram content never triggers an order. The only allowed output is a candidate research item. Historical backtesting and paper/shadow trading must independently validate any strategy. Existing risk controls, permission rules, strategy promotion gates, and explicit human approval for real-money trading remain authoritative and cannot be modified by this integration.

## 11. Phased implementation plan

1. **Design (this document):** agree provider, channel allowlist model, retention, and permissions.
2. **Connector contract:** typed provider interface and configuration schema; no network calls in unit tests.
3. **Ingestion core:** allowlist, normalizer, deduplication, edit tracking, size/rate limits.
4. **Security tests:** deny unknown channel, deny outbound methods, reject prompt-injection-like content as instructions, redact secrets, reject oversized payloads.
5. **Provider integration:** connect a user-controlled test channel using official API; secrets only in GitHub Actions secrets or local environment, never committed.
6. **Research handoff:** candidate-signal schema and human review; still no order execution.
7. **Shadow evaluation:** measure source quality and parser error rates before considering wider use.

## 12. Acceptance criteria

- Only explicitly allowlisted channel IDs are ingested.
- No group, personal-chat, or contact APIs are exposed.
- No outbound Telegram methods are implemented.
- Raw posts are treated as untrusted and never executed.
- Duplicate and edited messages are traceable and idempotent.
- Credentials are absent from source, logs, and test fixtures.
- Tests prove unknown channels are denied and no broker/order calls are possible.
- Telegram-derived candidates can only enter research/backtesting, never order execution.

This document records an architecture decision only. It does not claim that Telegram is connected or that any Telegram integration code exists yet.
