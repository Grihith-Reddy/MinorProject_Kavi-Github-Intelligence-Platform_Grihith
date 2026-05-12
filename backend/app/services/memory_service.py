import json
import logging
import re
from collections import Counter
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)

_QUERY_TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_./\\-]{2,}")
_QUERY_STOP_WORDS = {
    "about",
    "after",
    "before",
    "branch",
    "chat",
    "code",
    "context",
    "did",
    "does",
    "explain",
    "for",
    "from",
    "have",
    "into",
    "just",
    "line",
    "lines",
    "maybe",
    "need",
    "please",
    "pull",
    "repo",
    "repository",
    "show",
    "that",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
}

_ROLE_SET = {"user", "assistant", "system", "tool"}


def _safe_text(value: Any, max_chars: int = 1000) -> str:
    text_value = str(value or "").strip()
    if not text_value:
        return ""
    return text_value[:max_chars]


def _safe_iso_timestamp(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    text_value = str(value or "").strip()
    return text_value or None


def _extract_search_terms(query: str, limit: int = 10) -> list[str]:
    seen: set[str] = set()
    terms: list[str] = []
    for raw_token in _QUERY_TOKEN_RE.findall(str(query or "")):
        token = raw_token.strip("`'\"()[]{}<>,:;!?").replace("\\", "/").strip("/").lower()
        if len(token) < 3 or token in _QUERY_STOP_WORDS:
            continue
        if token in seen:
            continue
        seen.add(token)
        terms.append(token)
        if len(terms) >= limit:
            break
    return terms


def _conversation_title(seed_query: str | None) -> str:
    text_value = " ".join(str(seed_query or "").split()).strip()
    if not text_value:
        return "New conversation"
    if len(text_value) <= 90:
        return text_value
    return text_value[:87].rstrip() + "..."


def ensure_chat_conversation(
    db: Session,
    *,
    user_id: str,
    repo_id: str,
    conversation_id: str | None = None,
    seed_query: str | None = None,
) -> dict[str, Any]:
    if conversation_id:
        existing = db.execute(
            text(
                """
                SELECT id, user_id, repo_id, title, status, message_count, last_message_at, created_at, updated_at
                FROM chat_conversations
                WHERE id = :conversation_id
                  AND user_id = :user_id
                  AND repo_id = :repo_id
                """
            ),
            {"conversation_id": conversation_id, "user_id": user_id, "repo_id": repo_id},
        ).mappings().first()
        if existing:
            return dict(existing)

    latest = db.execute(
        text(
            """
            SELECT id, user_id, repo_id, title, status, message_count, last_message_at, created_at, updated_at
            FROM chat_conversations
            WHERE user_id = :user_id
              AND repo_id = :repo_id
              AND status = 'active'
            ORDER BY COALESCE(last_message_at, created_at) DESC
            LIMIT 1
            """
        ),
        {"user_id": user_id, "repo_id": repo_id},
    ).mappings().first()
    if latest:
        return dict(latest)

    created = db.execute(
        text(
            """
            INSERT INTO chat_conversations (
                id, user_id, repo_id, title, status, message_count, last_message_at
            )
            VALUES (
                gen_random_uuid(), :user_id, :repo_id, :title, 'active', 0, NOW()
            )
            RETURNING id, user_id, repo_id, title, status, message_count, last_message_at, created_at, updated_at
            """
        ),
        {
            "user_id": user_id,
            "repo_id": repo_id,
            "title": _conversation_title(seed_query),
        },
    ).mappings().first()
    return dict(created or {})


def append_chat_message(
    db: Session,
    *,
    conversation_id: str,
    user_id: str,
    repo_id: str,
    role: str,
    content: str,
    mode: str | None = None,
    answer_structured: dict[str, Any] | None = None,
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_role = str(role or "").strip().lower()
    if normalized_role not in _ROLE_SET:
        normalized_role = "user"

    structured_payload = answer_structured if isinstance(answer_structured, dict) else None
    sources_payload = sources if isinstance(sources, list) else None
    sanitized_content = _safe_text(content, max_chars=64000)

    inserted = db.execute(
        text(
            """
            INSERT INTO chat_messages (
                id,
                conversation_id,
                user_id,
                repo_id,
                role,
                content,
                mode,
                answer_structured,
                sources
            )
            VALUES (
                gen_random_uuid(),
                :conversation_id,
                :user_id,
                :repo_id,
                :role,
                :content,
                :mode,
                CAST(:answer_structured AS jsonb),
                CAST(:sources AS jsonb)
            )
            RETURNING id, role, content, mode, answer_structured, sources, created_at
            """
        ),
        {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "repo_id": repo_id,
            "role": normalized_role,
            "content": sanitized_content,
            "mode": _safe_text(mode, max_chars=32) or None,
            "answer_structured": json.dumps(structured_payload) if structured_payload is not None else None,
            "sources": json.dumps(sources_payload) if sources_payload is not None else None,
        },
    ).mappings().first()

    db.execute(
        text(
            """
            UPDATE chat_conversations
            SET
                updated_at = NOW(),
                last_message_at = NOW(),
                message_count = message_count + 1,
                title = CASE
                    WHEN :role = 'user' AND (title IS NULL OR btrim(title) = '')
                        THEN :title_seed
                    ELSE title
                END
            WHERE id = :conversation_id
            """
        ),
        {
            "conversation_id": conversation_id,
            "role": normalized_role,
            "title_seed": _conversation_title(sanitized_content),
        },
    )

    return dict(inserted or {})


def list_conversations(
    db: Session,
    *,
    user_id: str,
    repo_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT
                c.id,
                c.repo_id,
                c.title,
                c.status,
                c.message_count,
                c.last_message_at,
                c.created_at,
                c.updated_at,
                lm.role AS last_message_role,
                lm.content AS last_message_content,
                lm.created_at AS last_message_created_at
            FROM chat_conversations c
            LEFT JOIN LATERAL (
                SELECT role, content, created_at
                FROM chat_messages
                WHERE conversation_id = c.id
                ORDER BY created_at DESC
                LIMIT 1
            ) lm ON TRUE
            WHERE c.user_id = :user_id
              AND c.repo_id = :repo_id
            ORDER BY COALESCE(c.last_message_at, c.created_at) DESC
            LIMIT :limit
            """
        ),
        {"user_id": user_id, "repo_id": repo_id, "limit": max(1, min(limit, 100))},
    ).mappings().all()

    conversations: list[dict[str, Any]] = []
    for row in rows:
        conversations.append(
            {
                "id": str(row.get("id")),
                "repo_id": str(row.get("repo_id")),
                "title": _safe_text(row.get("title"), max_chars=120) or "Conversation",
                "status": str(row.get("status") or "active"),
                "message_count": int(row.get("message_count") or 0),
                "last_message_at": _safe_iso_timestamp(row.get("last_message_at")),
                "created_at": _safe_iso_timestamp(row.get("created_at")),
                "updated_at": _safe_iso_timestamp(row.get("updated_at")),
                "last_message": {
                    "role": str(row.get("last_message_role") or ""),
                    "content": _safe_text(row.get("last_message_content"), max_chars=320),
                    "created_at": _safe_iso_timestamp(row.get("last_message_created_at")),
                },
            }
        )
    return conversations


def get_conversation_with_messages(
    db: Session,
    *,
    user_id: str,
    conversation_id: str,
    limit: int = 200,
) -> dict[str, Any] | None:
    conversation = db.execute(
        text(
            """
            SELECT id, repo_id, title, status, message_count, last_message_at, created_at, updated_at
            FROM chat_conversations
            WHERE id = :conversation_id
              AND user_id = :user_id
            """
        ),
        {"conversation_id": conversation_id, "user_id": user_id},
    ).mappings().first()
    if not conversation:
        return None

    rows = db.execute(
        text(
            """
            SELECT id, role, content, mode, answer_structured, sources, created_at, updated_at
            FROM chat_messages
            WHERE conversation_id = :conversation_id
            ORDER BY created_at ASC
            LIMIT :limit
            """
        ),
        {"conversation_id": conversation_id, "limit": max(1, min(limit, 800))},
    ).mappings().all()

    messages: list[dict[str, Any]] = []
    for row in rows:
        messages.append(
            {
                "id": str(row.get("id")),
                "role": str(row.get("role") or "assistant"),
                "content": _safe_text(row.get("content"), max_chars=64000),
                "mode": _safe_text(row.get("mode"), max_chars=32) or None,
                "answer_structured": row.get("answer_structured"),
                "sources": row.get("sources"),
                "created_at": _safe_iso_timestamp(row.get("created_at")),
                "updated_at": _safe_iso_timestamp(row.get("updated_at")),
            }
        )

    return {
        "conversation": {
            "id": str(conversation.get("id")),
            "repo_id": str(conversation.get("repo_id")),
            "title": _safe_text(conversation.get("title"), max_chars=120) or "Conversation",
            "status": str(conversation.get("status") or "active"),
            "message_count": int(conversation.get("message_count") or 0),
            "last_message_at": _safe_iso_timestamp(conversation.get("last_message_at")),
            "created_at": _safe_iso_timestamp(conversation.get("created_at")),
            "updated_at": _safe_iso_timestamp(conversation.get("updated_at")),
        },
        "messages": messages,
    }


def _score_memory_row(row: dict[str, Any], *, repo_id: str, conversation_id: str, query_terms: list[str], order: int) -> float:
    score = 0.0
    confidence = float(row.get("confidence") or 0.0)
    score += confidence * 6.0

    row_repo_id = str(row.get("repo_id") or "")
    row_conversation_id = str(row.get("conversation_id") or "")
    scope = str(row.get("memory_scope") or "")

    if scope == "repo" and row_repo_id == repo_id:
        score += 3.0
    if scope == "conversation" and row_conversation_id == conversation_id:
        score += 2.5
    if scope == "user":
        score += 1.0

    haystack = " ".join(
        [
            str(row.get("kind") or "").lower(),
            str(row.get("key") or "").lower(),
            str(row.get("value") or "").lower(),
        ]
    )
    score += max(0.0, 2.5 - (order * 0.02))
    for term in query_terms:
        if term in haystack:
            score += 1.3
    return score


def _compact_message_rows(rows: list[dict[str, Any]], max_chars: int = 900) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for row in rows:
        compact.append(
            {
                "id": str(row.get("id")),
                "role": str(row.get("role") or ""),
                "content": _safe_text(row.get("content"), max_chars=max_chars),
                "mode": _safe_text(row.get("mode"), max_chars=32) or None,
                "created_at": _safe_iso_timestamp(row.get("created_at")),
            }
        )
    return compact


def _fetch_recent_messages(
    db: Session,
    *,
    conversation_id: str,
    limit: int,
) -> list[dict[str, Any]]:
    rows = db.execute(
        text(
            """
            SELECT id, role, content, mode, created_at
            FROM chat_messages
            WHERE conversation_id = :conversation_id
            ORDER BY created_at DESC
            LIMIT :limit
            """
        ),
        {"conversation_id": conversation_id, "limit": max(1, min(limit, 100))},
    ).mappings().all()
    ordered = list(reversed([dict(row) for row in rows]))
    return ordered


def _fetch_relevant_messages(
    db: Session,
    *,
    conversation_id: str,
    query: str,
    limit: int,
) -> list[dict[str, Any]]:
    query_text = _safe_text(query, max_chars=2000)
    if not query_text:
        return []

    relevant_rows: list[dict[str, Any]] = []
    try:
        ts_rows = db.execute(
            text(
                """
                SELECT
                    id,
                    role,
                    content,
                    mode,
                    created_at,
                    ts_rank(search_document, plainto_tsquery('english', :query)) AS rank
                FROM chat_messages
                WHERE conversation_id = :conversation_id
                  AND search_document @@ plainto_tsquery('english', :query)
                ORDER BY rank DESC, created_at DESC
                LIMIT :limit
                """
            ),
            {"conversation_id": conversation_id, "query": query_text, "limit": max(1, min(limit, 30))},
        ).mappings().all()
        relevant_rows = [dict(row) for row in ts_rows]
    except Exception:
        db.rollback()
        logger.warning("Failed to run full-text memory retrieval over chat messages", exc_info=True)

    if relevant_rows:
        return relevant_rows

    try:
        ilike_rows = db.execute(
            text(
                """
                SELECT id, role, content, mode, created_at
                FROM chat_messages
                WHERE conversation_id = :conversation_id
                  AND content ILIKE :query
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {
                "conversation_id": conversation_id,
                "query": f"%{query_text[:180]}%",
                "limit": max(1, min(limit, 20)),
            },
        ).mappings().all()
        return [dict(row) for row in ilike_rows]
    except Exception:
        db.rollback()
        logger.warning("Failed to run lexical memory retrieval over chat messages", exc_info=True)
        return []


def _fetch_repo_snapshot(db: Session, *, user_id: str, repo_id: str) -> dict[str, Any]:
    repositories = db.execute(
        text(
            """
            SELECT
                r.id,
                r.full_name,
                r.default_branch,
                r.synced_at,
                COALESCE(pr_counts.pr_count, 0) AS pr_count
            FROM repositories r
            JOIN repository_access ra ON ra.repository_id = r.id
            JOIN github_accounts ga ON ga.id = ra.github_account_id
            LEFT JOIN (
                SELECT repo_id, COUNT(*) AS pr_count
                FROM pull_requests
                GROUP BY repo_id
            ) pr_counts ON pr_counts.repo_id = r.id
            WHERE ga.user_id = :user_id
            ORDER BY COALESCE(r.synced_at, r.updated_at, r.created_at) DESC
            LIMIT 24
            """
        ),
        {"user_id": user_id},
    ).mappings().all()

    recent_prs = db.execute(
        text(
            """
            SELECT github_pr_number, title, state, author_login, merged_at, created_at, updated_at
            FROM pull_requests
            WHERE repo_id = :repo_id
            ORDER BY COALESCE(merged_at, updated_at, created_at) DESC
            LIMIT 12
            """
        ),
        {"repo_id": repo_id},
    ).mappings().all()

    hot_files = db.execute(
        text(
            """
            SELECT file_path, COUNT(*) AS change_count
            FROM file_mappings
            WHERE repo_id = :repo_id
            GROUP BY file_path
            ORDER BY change_count DESC
            LIMIT 16
            """
        ),
        {"repo_id": repo_id},
    ).mappings().all()

    return {
        "known_repositories": [
            {
                "repo_id": str(row.get("id")),
                "full_name": _safe_text(row.get("full_name"), max_chars=240),
                "default_branch": _safe_text(row.get("default_branch"), max_chars=80) or None,
                "synced_at": _safe_iso_timestamp(row.get("synced_at")),
                "pr_count": int(row.get("pr_count") or 0),
            }
            for row in repositories
        ],
        "recent_pull_requests": [
            {
                "github_pr_number": row.get("github_pr_number"),
                "title": _safe_text(row.get("title"), max_chars=220),
                "state": _safe_text(row.get("state"), max_chars=32),
                "author_login": _safe_text(row.get("author_login"), max_chars=80),
                "merged_at": _safe_iso_timestamp(row.get("merged_at")),
                "created_at": _safe_iso_timestamp(row.get("created_at")),
                "updated_at": _safe_iso_timestamp(row.get("updated_at")),
            }
            for row in recent_prs
        ],
        "hot_files": [
            {
                "file_path": _safe_text(row.get("file_path"), max_chars=260),
                "change_count": int(row.get("change_count") or 0),
            }
            for row in hot_files
        ],
    }


def build_memory_context(
    db: Session,
    *,
    user_id: str,
    repo_id: str,
    conversation: dict[str, Any],
    query: str,
    exclude_message_ids: list[str] | None = None,
    recent_limit: int = 12,
    relevant_limit: int = 8,
    memory_limit: int = 16,
) -> dict[str, Any]:
    conversation_id = str(conversation.get("id") or "")
    exclude_set = {str(item) for item in (exclude_message_ids or []) if str(item).strip()}

    recent_messages = _fetch_recent_messages(db, conversation_id=conversation_id, limit=max(recent_limit + 4, 8))
    recent_messages = [row for row in recent_messages if str(row.get("id")) not in exclude_set][-recent_limit:]

    relevant_messages = _fetch_relevant_messages(
        db,
        conversation_id=conversation_id,
        query=query,
        limit=max(relevant_limit + 3, 6),
    )
    relevant_messages = [row for row in relevant_messages if str(row.get("id")) not in exclude_set][:relevant_limit]

    memory_rows = db.execute(
        text(
            """
            SELECT
                id,
                user_id,
                repo_id,
                conversation_id,
                memory_scope,
                kind,
                key,
                value,
                confidence,
                last_seen_at,
                created_at
            FROM chat_memory_items
            WHERE user_id = :user_id
              AND archived_at IS NULL
              AND (repo_id = :repo_id OR repo_id IS NULL)
            ORDER BY last_seen_at DESC
            LIMIT 240
            """
        ),
        {"user_id": user_id, "repo_id": repo_id},
    ).mappings().all()

    query_terms = _extract_search_terms(query, limit=10)
    scored_rows: list[tuple[float, dict[str, Any]]] = []
    for idx, row in enumerate(memory_rows):
        row_dict = dict(row)
        score = _score_memory_row(
            row_dict,
            repo_id=repo_id,
            conversation_id=conversation_id,
            query_terms=query_terms,
            order=idx,
        )
        scored_rows.append((score, row_dict))

    memory_items: list[dict[str, Any]] = []
    seen_memory_keys: set[tuple[str, str, str]] = set()
    for _, row in sorted(scored_rows, key=lambda item: item[0], reverse=True):
        signature = (
            str(row.get("memory_scope") or ""),
            str(row.get("kind") or "").lower(),
            str(row.get("key") or "").strip().lower(),
        )
        if signature in seen_memory_keys:
            continue
        seen_memory_keys.add(signature)
        memory_items.append(
            {
                "id": str(row.get("id")),
                "scope": str(row.get("memory_scope") or ""),
                "kind": _safe_text(row.get("kind"), max_chars=48),
                "key": _safe_text(row.get("key"), max_chars=120),
                "value": _safe_text(row.get("value"), max_chars=360),
                "confidence": float(row.get("confidence") or 0.0),
                "last_seen_at": _safe_iso_timestamp(row.get("last_seen_at")),
            }
        )
        if len(memory_items) >= max(4, min(memory_limit, 30)):
            break

    repo_snapshot = _fetch_repo_snapshot(db, user_id=user_id, repo_id=repo_id)
    conversation_message_count = int(conversation.get("message_count") or 0)
    if conversation_message_count <= 0:
        conversation_message_count = len(recent_messages)

    return {
        "conversation": {
            "id": conversation_id,
            "title": _safe_text(conversation.get("title"), max_chars=120) or "Conversation",
            "status": _safe_text(conversation.get("status"), max_chars=20) or "active",
            "message_count": conversation_message_count,
            "last_message_at": _safe_iso_timestamp(conversation.get("last_message_at")),
        },
        "recent_messages": _compact_message_rows(recent_messages, max_chars=820),
        "relevant_messages": _compact_message_rows(relevant_messages, max_chars=760),
        "memory_items": memory_items,
        "repo_snapshot": repo_snapshot,
    }


def _normalize_memory_scope(scope: Any) -> str:
    normalized = str(scope or "").strip().lower()
    if normalized in {"user", "repo", "conversation"}:
        return normalized
    return "conversation"


def deduplicate_memory_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        scope = _normalize_memory_scope(item.get("memory_scope"))
        kind = _safe_text(item.get("kind"), max_chars=48).lower()
        key = _safe_text(item.get("key"), max_chars=120)
        value = _safe_text(item.get("value"), max_chars=600)
        if not kind or not key or not value:
            continue
        signature = (scope, kind, key.strip().lower())
        confidence = float(item.get("confidence") or 0.5)
        normalized_item = {
            "memory_scope": scope,
            "kind": kind,
            "key": key,
            "value": value,
            "confidence": max(0.1, min(confidence, 0.99)),
            "source_payload": item.get("source_payload") if isinstance(item.get("source_payload"), dict) else None,
        }
        previous = deduped.get(signature)
        if previous is None or float(previous.get("confidence") or 0.0) <= normalized_item["confidence"]:
            deduped[signature] = normalized_item
    return list(deduped.values())


def extract_turn_memory_items(
    *,
    query: str,
    answer: str,
    structured: dict[str, Any] | None,
    sources: list[dict[str, Any]] | None,
    repo_meta: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    memory_items: list[dict[str, Any]] = []
    normalized_query = " ".join(str(query or "").split()).strip()
    query_lower = normalized_query.lower()

    repo_full_name = _safe_text((repo_meta or {}).get("full_name"), max_chars=240)
    if repo_full_name:
        memory_items.append(
            {
                "memory_scope": "repo",
                "kind": "repository",
                "key": repo_full_name,
                "value": (
                    f"Repository context: {repo_full_name}"
                    f" (default branch: {_safe_text((repo_meta or {}).get('default_branch'), max_chars=48) or 'unknown'})"
                ),
                "confidence": 0.95,
                "source_payload": {"repo_id": str((repo_meta or {}).get("id") or "")},
            }
        )

    language_counter: Counter[str] = Counter()
    language_hints = {
        "python": "python",
        "typescript": "typescript",
        "javascript": "javascript",
        "java": "java",
        "kotlin": "kotlin",
        "go": "go",
        "rust": "rust",
        "c#": "csharp",
        "csharp": "csharp",
        "sql": "sql",
        "shell": "shell",
    }
    for needle, normalized in language_hints.items():
        if needle in query_lower:
            language_counter[normalized] += 1

    if any(token in query_lower for token in ("prefer", "use ", "using ", "stick to")) and language_counter:
        top_language = language_counter.most_common(1)[0][0]
        memory_items.append(
            {
                "memory_scope": "user",
                "kind": "preference",
                "key": "preferred_language",
                "value": f"User prefers {top_language} examples when possible.",
                "confidence": 0.78,
                "source_payload": {"query": normalized_query[:220]},
            }
        )

    task_match = re.search(
        r"\b(?:we|i)\s+(?:need to|want to|are trying to|must)\s+([a-zA-Z0-9 ,._/#-]{12,220})",
        normalized_query,
        flags=re.IGNORECASE,
    )
    if task_match:
        task_value = _safe_text(task_match.group(1), max_chars=220)
        if task_value:
            memory_items.append(
                {
                    "memory_scope": "conversation",
                    "kind": "active_task",
                    "key": "current_task",
                    "value": task_value,
                    "confidence": 0.73,
                    "source_payload": {"query": normalized_query[:220]},
                }
            )

    if re.match(r"^(implement|build|fix|refactor|add|create|improve)\b", query_lower):
        memory_items.append(
            {
                "memory_scope": "conversation",
                "kind": "active_task",
                "key": "current_task",
                "value": _safe_text(normalized_query, max_chars=220),
                "confidence": 0.68,
                "source_payload": {"query": normalized_query[:220]},
            }
        )

    normalized_sources = sources if isinstance(sources, list) else []
    for source in normalized_sources[:6]:
        if not isinstance(source, dict):
            continue
        pr_number = source.get("pr_number")
        pr_title = _safe_text(source.get("pr_title"), max_chars=260)
        if pr_number:
            memory_items.append(
                {
                    "memory_scope": "repo",
                    "kind": "pull_request",
                    "key": f"pr#{pr_number}",
                    "value": pr_title or f"Pull request #{pr_number}",
                    "confidence": 0.84,
                    "source_payload": {"pr_number": pr_number},
                }
            )

        files = source.get("files") if isinstance(source.get("files"), list) else []
        for file_info in files[:3]:
            if not isinstance(file_info, dict):
                continue
            file_path = _safe_text(file_info.get("file_path"), max_chars=260)
            if not file_path:
                continue
            memory_items.append(
                {
                    "memory_scope": "repo",
                    "kind": "file",
                    "key": file_path,
                    "value": f"Frequently referenced file: {file_path}",
                    "confidence": 0.74,
                    "source_payload": {
                        "start_line": file_info.get("start_line"),
                        "end_line": file_info.get("end_line"),
                        "pr_number": pr_number,
                    },
                }
            )

    structured_payload = structured if isinstance(structured, dict) else {}
    summary_text = _safe_text(structured_payload.get("summary"), max_chars=420)
    if not summary_text:
        summary_text = _safe_text(answer, max_chars=420)
    if summary_text:
        memory_items.append(
            {
                "memory_scope": "conversation",
                "kind": "assistant_summary",
                "key": "latest_response_summary",
                "value": summary_text,
                "confidence": 0.67,
                "source_payload": {
                    "title": _safe_text(structured_payload.get("title"), max_chars=120),
                },
            }
        )

    sections = structured_payload.get("sections") if isinstance(structured_payload.get("sections"), list) else []
    for section in sections[:3]:
        if not isinstance(section, dict):
            continue
        heading = _safe_text(section.get("heading"), max_chars=80)
        bullets = section.get("bullets") if isinstance(section.get("bullets"), list) else []
        if not heading or not bullets:
            continue
        top_bullet = _safe_text(bullets[0], max_chars=220)
        if not top_bullet:
            continue
        memory_items.append(
            {
                "memory_scope": "conversation",
                "kind": "insight",
                "key": heading,
                "value": top_bullet,
                "confidence": 0.61,
                "source_payload": {"heading": heading},
            }
        )

    return deduplicate_memory_items(memory_items)


def upsert_memory_items(
    db: Session,
    *,
    user_id: str,
    repo_id: str,
    conversation_id: str,
    source_message_id: str | None,
    memory_items: list[dict[str, Any]],
) -> None:
    normalized_items = deduplicate_memory_items(memory_items)
    for item in normalized_items:
        scope = _normalize_memory_scope(item.get("memory_scope"))
        kind = _safe_text(item.get("kind"), max_chars=48).lower()
        key = _safe_text(item.get("key"), max_chars=120)
        value = _safe_text(item.get("value"), max_chars=600)
        confidence = max(0.1, min(float(item.get("confidence") or 0.5), 0.99))
        if not kind or not key or not value:
            continue

        scoped_repo_id = repo_id if scope == "repo" else None
        scoped_conversation_id = conversation_id if scope == "conversation" else None
        source_payload = item.get("source_payload") if isinstance(item.get("source_payload"), dict) else None

        existing = db.execute(
            text(
                """
                SELECT id, confidence
                FROM chat_memory_items
                WHERE user_id = :user_id
                  AND memory_scope = :memory_scope
                  AND kind = :kind
                  AND key = :key
                  AND (
                    (:repo_id IS NULL AND repo_id IS NULL)
                    OR repo_id = :repo_id
                  )
                  AND (
                    (:conversation_id IS NULL AND conversation_id IS NULL)
                    OR conversation_id = :conversation_id
                  )
                LIMIT 1
                """
            ),
            {
                "user_id": user_id,
                "memory_scope": scope,
                "kind": kind,
                "key": key,
                "repo_id": scoped_repo_id,
                "conversation_id": scoped_conversation_id,
            },
        ).mappings().first()

        if existing:
            existing_confidence = float(existing.get("confidence") or 0.0)
            db.execute(
                text(
                    """
                    UPDATE chat_memory_items
                    SET
                        value = :value,
                        confidence = :confidence,
                        source_message_id = :source_message_id,
                        source_payload = CAST(:source_payload AS jsonb),
                        archived_at = NULL,
                        last_seen_at = NOW(),
                        updated_at = NOW()
                    WHERE id = :id
                    """
                ),
                {
                    "id": existing.get("id"),
                    "value": value,
                    "confidence": max(existing_confidence, confidence),
                    "source_message_id": source_message_id,
                    "source_payload": json.dumps(source_payload) if source_payload is not None else None,
                },
            )
            continue

        db.execute(
            text(
                """
                INSERT INTO chat_memory_items (
                    id,
                    user_id,
                    repo_id,
                    conversation_id,
                    source_message_id,
                    memory_scope,
                    kind,
                    key,
                    value,
                    confidence,
                    source_payload,
                    last_seen_at
                )
                VALUES (
                    gen_random_uuid(),
                    :user_id,
                    :repo_id,
                    :conversation_id,
                    :source_message_id,
                    :memory_scope,
                    :kind,
                    :key,
                    :value,
                    :confidence,
                    CAST(:source_payload AS jsonb),
                    NOW()
                )
                """
            ),
            {
                "user_id": user_id,
                "repo_id": scoped_repo_id,
                "conversation_id": scoped_conversation_id,
                "source_message_id": source_message_id,
                "memory_scope": scope,
                "kind": kind,
                "key": key,
                "value": value,
                "confidence": confidence,
                "source_payload": json.dumps(source_payload) if source_payload is not None else None,
            },
        )

