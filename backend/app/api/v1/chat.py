import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.rate_limit import enforce_rate_limit
from app.db.session import SessionLocal, get_db
from app.models.models import Conversation, Message, UsageEvent, User
from app.schemas.schemas import ChatRequest, ConversationOut, MessageOut
from app.services import generation
from app.services.retrieval.retriever import retrieve

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/conversations", response_model=list[ConversationOut])
def list_conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(
        select(Conversation)
        .where(Conversation.user_id == user.id)
        .order_by(Conversation.updated_at.desc())
        .limit(100)
    ).all()


@router.get("/conversations/{conversation_id}/messages", response_model=list[MessageOut])
def list_messages(
    conversation_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    _own_conversation_or_404(db, conversation_id, user)
    return db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    ).all()


@router.post("/stream")
def chat_stream(
    request: Request,
    payload: ChatRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """SSE stream. Event sequence:
    meta -> token* -> citations -> done   (grounded path)
    meta -> notfound -> done              (grounding gate refused)
    """
    enforce_rate_limit(request, "chat", str(user.id))

    if payload.conversation_id:
        conversation = _own_conversation_or_404(db, payload.conversation_id, user)
    else:
        conversation = Conversation(user_id=user.id, title=payload.question[:80])
        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    history_rows = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.created_at)
    ).all()
    history = [{"role": m.role, "content": m.content} for m in history_rows]
    conversation_id = conversation.id
    question = payload.question
    filters = payload.filters
    top_k = payload.top_k
    user_id = user.id

    def event_generator():
        # This generator outlives the request-scoped session, so it owns one.
        session = SessionLocal()
        started = time.monotonic()
        try:
            session.add(Message(conversation_id=conversation_id, role="user", content=question))
            session.commit()

            yield {"event": "meta", "data": json.dumps({"conversation_id": str(conversation_id)})}

            search_query = generation.rewrite_query(question, history)
            result = retrieve(session, search_query, filters=filters, top_k=top_k)

            if not result.grounded:
                answer = generation.NOT_FOUND_MESSAGE
                yield {"event": "notfound", "data": answer}
                citations: list[dict] = []
                grounded = False
            else:
                parts: list[str] = []
                for token in generation.stream_grounded_answer(question, result.chunks, history):
                    parts.append(token)
                    yield {"event": "token", "data": token}
                answer = "".join(parts)
                citations = generation.citations_from_chunks(result.chunks, answer)
                yield {"event": "citations", "data": json.dumps(citations)}
                grounded = True

            latency_ms = int((time.monotonic() - started) * 1000)
            session.add(
                Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=answer,
                    citations=citations,
                    grounded=grounded,
                    latency_ms=latency_ms,
                )
            )
            session.add(
                UsageEvent(
                    user_id=user_id,
                    event_type="chat",
                    duration_ms=latency_ms,
                    meta={"grounded": grounded, "chunks": len(result.chunks)},
                )
            )
            session.commit()
            yield {"event": "done", "data": json.dumps({"latency_ms": latency_ms, "grounded": grounded})}
        except Exception as exc:  # surface a clean error event, log server-side
            session.rollback()
            from app.core.logging import get_logger

            get_logger(__name__).exception("chat stream failed")
            yield {"event": "error", "data": json.dumps({"detail": type(exc).__name__})}
        finally:
            session.close()

    return EventSourceResponse(event_generator())


def _own_conversation_or_404(db: Session, conversation_id: uuid.UUID, user: User) -> Conversation:
    conversation = db.get(Conversation, conversation_id)
    if not conversation or conversation.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    return conversation
