"""
Chatbot router, GET /chat/history and POST /chat/message.

Conversations and messages are persisted to the Chat History entity so the
sidebar survives a page reload and the assistant can use recent turns as
context.
"""

from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.ai import chatbot
from app.core.deps import get_current_user, require_customer
from app.database import get_db
from app.models.chat import ChatConversation, ChatMessage
from app.models.customer import Customer
from app.schemas.ai import ChatHistoryOut, ChatMessageRequest, ChatReply
from app.schemas.common import CamelModel

router = APIRouter(prefix="/chat", tags=["AI Chatbot"])


def _relative_day(value: datetime) -> str:
    """Render a timestamp the way the chat sidebar labels it."""
    if value is None:
        return ""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    delta_days = (date.today() - value.date()).days
    if delta_days <= 0:
        return "Today"
    if delta_days == 1:
        return "Yesterday"
    if delta_days <= 7:
        return "Last week"
    return value.date().isoformat()


@router.get("/history", response_model=list[ChatHistoryOut])
def get_history(
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    conversations = (
        db.query(ChatConversation)
        .filter(ChatConversation.customer_id == current_user.customer_id)
        .order_by(ChatConversation.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": f"c-{conversation.conversation_id}",
            "title": conversation.title,
            "date": _relative_day(conversation.created_at),
        }
        for conversation in conversations
    ]


class ChatMessageOut(CamelModel):
    """One turn of a stored conversation."""

    id: str
    role: str            # 'user' | 'assistant'
    content: str
    time: str            # HH:MM, matching what the page prints on live replies


class ConversationOut(CamelModel):
    id: str
    title: str
    date: str
    messages: list[ChatMessageOut]


def _conversation_or_404(db: Session, conversation_id: str, customer_id: str) -> ChatConversation:
    """
    Resolve a 'c-12' style id to a conversation this customer owns.

    The ownership check is the access control, and it deliberately returns 404
    rather than 403 for someone else's thread: a 403 would confirm that the
    conversation exists.
    """
    raw = str(conversation_id)
    if raw.startswith("c-"):
        raw = raw[2:]
    try:
        numeric = int(raw)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    conversation = db.get(ChatConversation, numeric)
    if conversation is None or conversation.customer_id != customer_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


@router.get("/history/{conversation_id}", response_model=ConversationOut)
def get_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(get_current_user),
):
    """
    One past conversation, with its messages.

    The sidebar listed conversations and clicking one did nothing, because
    there was no way to fetch its contents. This is that way.
    """
    conversation = _conversation_or_404(db, conversation_id, current_user.customer_id)

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.conversation_id == conversation.conversation_id)
        .order_by(ChatMessage.created_at, ChatMessage.message_id)
        .all()
    )

    return {
        "id": f"c-{conversation.conversation_id}",
        "title": conversation.title,
        "date": _relative_day(conversation.created_at),
        "messages": [
            {
                "id": f"m-{message.message_id}",
                "role": message.role,
                "content": message.content,
                "time": (message.created_at or datetime.now(UTC)).strftime("%H:%M"),
            }
            for message in messages
        ],
    }


@router.delete("/history/{conversation_id}")
def delete_conversation(
    conversation_id: str,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(require_customer),
):
    """Remove a conversation and its messages. Backs the bin icon in the sidebar."""
    conversation = _conversation_or_404(db, conversation_id, current_user.customer_id)
    db.delete(conversation)
    db.commit()
    return {"deleted": True, "id": f"c-{conversation.conversation_id}"}


@router.post("/message", response_model=ChatReply)
def send_message(
    payload: ChatMessageRequest,
    db: Session = Depends(get_db),
    current_user: Customer = Depends(require_customer),
):
    """Answer a customer question and persist both sides of the exchange."""
    conversation: ChatConversation | None = None

    if payload.conversation_id is not None:
        conversation = db.get(ChatConversation, payload.conversation_id)
        if conversation is not None and conversation.customer_id != current_user.customer_id:
            conversation = None  # never leak another customer's thread

    if conversation is None:
        conversation = ChatConversation(
            customer_id=current_user.customer_id,
            title=chatbot.suggest_title(payload.message),
        )
        db.add(conversation)
        db.flush()

    # Recent turns give the assistant short-term memory.
    history = [
        {"role": message.role, "content": message.content}
        for message in (
            db.query(ChatMessage)
            .filter(ChatMessage.conversation_id == conversation.conversation_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(6)
            .all()
        )
    ][::-1]

    reply_text = chatbot.answer(db, current_user, payload.message, history)

    db.add(
        ChatMessage(
            conversation_id=conversation.conversation_id,
            role="user",
            content=payload.message,
        )
    )
    db.add(
        ChatMessage(
            conversation_id=conversation.conversation_id,
            role="assistant",
            content=reply_text,
        )
    )
    db.commit()

    return {"reply": reply_text, "conversation_id": conversation.conversation_id}
