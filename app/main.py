import os
import re
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import Base, SessionLocal, engine, get_db
from app.models import Article, ArticleChunk, Bookmark, Feedback, SearchLog, Ticket, TicketComment, User
from app.security import create_access_token, decode_access_token, hash_password, verify_password
from app.seed import seed_articles
from app.services.rag import AI_ENABLED, generate_answer, index_article, retrieve, split_into_chunks

BASE_DIR = Path(__file__).resolve().parent.parent
app = FastAPI(title="Nexus Support", description="Grounded technical knowledge search and support tickets")
bearer = HTTPBearer(auto_error=False)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
CATEGORIES = ["Hardware", "Software", "Network", "Database", "Cloud", "Security", "Programming"]


class RegisterInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)


class ArticleInput(BaseModel):
    title: str = Field(min_length=4, max_length=240)
    summary: str = Field(default="", max_length=500)
    content: str = Field(min_length=10, max_length=30000)
    category: str = Field(min_length=2, max_length=80)
    technology: str = Field(default="", max_length=100)
    product: str = Field(default="", max_length=100)
    error_code: str = Field(default="", max_length=120)
    difficulty: str = Field(default="Beginner", max_length=20)
    tags: str = Field(default="", max_length=500)


class TicketInput(BaseModel):
    subject: str = Field(min_length=4, max_length=240)
    description: str = Field(min_length=10, max_length=10000)
    priority: str = Field(default="Medium", pattern="^(Low|Medium|High|Critical)$")


class TicketUpdate(BaseModel):
    status: str | None = Field(default=None, pattern="^(Open|In Progress|Resolved|Closed)$")
    assignee_id: int | None = None
    comment: str | None = Field(default=None, max_length=5000)


class FeedbackInput(BaseModel):
    article_id: int
    helpful: bool


class RoleUpdate(BaseModel):
    role: str = Field(pattern="^(user|agent|admin)$")


class LoginInput(BaseModel):
    email: EmailStr
    password: str


def user_view(user: User) -> dict:
    return {"id": user.id, "name": user.name, "email": user.email, "role": user.role, "created_at": user.created_at}


def article_view(article: Article, score: float | None = None) -> dict:
    result = {
        "id": article.id, "title": article.title, "summary": article.summary,
        "content": article.content, "category": article.category, "technology": article.technology,
        "product": article.product, "error_code": article.error_code, "difficulty": article.difficulty,
        "tags": article.tags, "source": article.source, "created_at": article.created_at,
    }
    if score is not None:
        result["score"] = round(score, 3)
    return result


def ticket_view(ticket: Ticket, include_comments: bool = False) -> dict:
    result = {
        "id": ticket.id, "ticket_key": ticket.ticket_key, "subject": ticket.subject,
        "description": ticket.description, "priority": ticket.priority, "status": ticket.status,
        "owner_id": ticket.owner_id, "owner_name": ticket.owner.name if ticket.owner else "",
        "assignee_id": ticket.assignee_id, "created_at": ticket.created_at, "updated_at": ticket.updated_at,
    }
    if include_comments:
        result["comments"] = [
            {"id": comment.id, "content": comment.content, "author": comment.author.name, "created_at": comment.created_at}
            for comment in ticket.comments
        ]
    return result


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Sign in to continue")
    subject = decode_access_token(credentials.credentials)
    user = db.get(User, int(subject)) if subject and subject.isdigit() else None
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


def optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User | None:
    if not credentials:
        return None
    subject = decode_access_token(credentials.credentials)
    return db.get(User, int(subject)) if subject and subject.isdigit() else None


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have permission to perform this action")
        return user
    return dependency


def ensure_ticket_access(ticket: Ticket, user: User) -> None:
    if user.role == "admin" or ticket.owner_id == user.id or (user.role == "agent" and ticket.assignee_id == user.id):
        return
    raise HTTPException(status_code=404, detail="Ticket not found")


@app.on_event("startup")
async def startup() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_articles(db)
        articles_without_chunks = db.scalars(select(Article).where(~Article.chunks.any())).all()
        for article in articles_without_chunks:
            article.chunks.extend(
                ArticleChunk(chunk_index=index, content=content)
                for index, content in enumerate(split_into_chunks(f"{article.title}\n{article.summary}\n{article.content}"))
            )
        db.commit()
        if os.getenv("GEMINI_API_KEY"):
            articles_missing_embeddings = db.scalars(
                select(Article).where(Article.chunks.any(ArticleChunk.embedding == ""))
            ).all()
            for article in articles_missing_embeddings:
                await index_article(db, article)
        admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD", "")
        if admin_email and len(admin_password) >= 16 and not db.scalar(select(User.id).where(User.email == admin_email)):
            db.add(User(name="Workspace Admin", email=admin_email, password_hash=hash_password(admin_password), role="admin"))
            db.commit()


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "ai_enabled": AI_ENABLED}


@app.post("/api/auth/register", status_code=201)
def register(payload: RegisterInput, db: Session = Depends(get_db)) -> dict:
    email = payload.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(name=payload.name.strip(), email=email, password_hash=hash_password(payload.password), role="user")
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"access_token": create_access_token(str(user.id)), "token_type": "bearer", "user": user_view(user)}


@app.post("/api/auth/login")
def login(payload: LoginInput, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return {"access_token": create_access_token(str(user.id)), "token_type": "bearer", "user": user_view(user)}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)) -> dict:
    return user_view(user)


@app.get("/api/categories")
def categories(db: Session = Depends(get_db)) -> dict:
    stored = db.scalars(select(Article.category).distinct().order_by(Article.category)).all()
    return {"categories": stored or CATEGORIES}


@app.get("/api/agents")
def agents(_user: User = Depends(require_roles("admin", "agent")), db: Session = Depends(get_db)) -> dict:
    staff = db.scalars(select(User).where(User.role.in_(["agent", "admin"])).order_by(User.name)).all()
    return {"agents": [{"id": person.id, "name": person.name, "role": person.role} for person in staff]}


@app.post("/api/search")
async def search(
    payload: dict,
    category: str | None = None,
    technology: str | None = None,
    product: str | None = None,
    error_code: str | None = None,
    difficulty: str | None = None,
    tag: str | None = None,
    date_after: str | None = None,
    user: User | None = Depends(optional_user),
    db: Session = Depends(get_db),
) -> dict:
    query = str(payload.get("query", "")).strip()[:500]
    if len(query) < 3:
        raise HTTPException(status_code=422, detail="Enter at least 3 characters")
    detected = list(dict.fromkeys(re.findall(r"\b[A-Z][A-Za-z]*(?:Error|Exception)\b|\b(?:HTTP\s*)?\d{3,5}\b", query, re.IGNORECASE)))
    results = await retrieve(db, query, category=category, technology=technology, product=product,
                             error_code=error_code or (detected[0] if detected else None), difficulty=difficulty,
                             tag=tag, date_after=date_after)
    answer = await generate_answer(query, results)
    db.add(SearchLog(user_id=user.id if user else None, query=query, results_count=len(results)))
    db.commit()
    return {
        "query": query,
        "answer": answer,
        "detected_errors": detected,
        "confidence": round(results[0][1], 3) if results else 0,
        "results": [article_view(article, score) for article, score in results],
        "ai_generated": bool(AI_ENABLED and results),
    }


@app.get("/api/search/suggestions")
def suggestions(q: str = Query(min_length=2, max_length=100), db: Session = Depends(get_db)) -> dict:
    articles = db.scalars(select(Article).where(Article.title.ilike(f"%{q}%")).limit(5)).all()
    common = db.scalars(select(SearchLog.query).where(SearchLog.query.ilike(f"%{q}%")).group_by(SearchLog.query).order_by(func.count(SearchLog.id).desc()).limit(5)).all()
    return {"suggestions": list(dict.fromkeys([article.title for article in articles] + common))[:7]}


@app.get("/api/articles")
def list_articles(
    q: str | None = None, category: str | None = None, tag: str | None = None,
    db: Session = Depends(get_db),
) -> dict:
    statement = select(Article).order_by(Article.created_at.desc())
    if q:
        statement = statement.where((Article.title.ilike(f"%{q}%")) | Article.content.ilike(f"%{q}%"))
    if category:
        statement = statement.where(Article.category.ilike(f"%{category}%"))
    if tag:
        statement = statement.where(Article.tags.ilike(f"%{tag}%"))
    return {"articles": [article_view(item) for item in db.scalars(statement.limit(100)).all()]}


@app.post("/api/articles", status_code=201)
async def create_article(payload: ArticleInput, user: User = Depends(require_roles("admin", "agent")), db: Session = Depends(get_db)) -> dict:
    article = Article(**payload.model_dump(), created_by=user.id)
    db.add(article)
    await index_article(db, article)
    db.commit()
    db.refresh(article)
    return article_view(article)


@app.put("/api/articles/{article_id}")
async def update_article(article_id: int, payload: ArticleInput, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)) -> dict:
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    for key, value in payload.model_dump().items():
        setattr(article, key, value)
    await index_article(db, article)
    db.commit()
    return article_view(article)


@app.delete("/api/articles/{article_id}", status_code=204)
def delete_article(article_id: int, _user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)) -> None:
    article = db.get(Article, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    db.delete(article)
    db.commit()


@app.post("/api/articles/upload", status_code=201)
async def upload_article(
    file: UploadFile = File(...), category: str = "Software", user: User = Depends(require_roles("admin", "agent")),
    db: Session = Depends(get_db),
) -> dict:
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in {".txt", ".md", ".pdf", ".docx"}:
        raise HTTPException(status_code=415, detail="Upload a TXT, Markdown, PDF, or DOCX file")
    contents = await file.read(10_000_001)
    if len(contents) > 10_000_000:
        raise HTTPException(status_code=413, detail="File must be 10 MB or smaller")
    try:
        if suffix == ".pdf":
            from io import BytesIO
            from pypdf import PdfReader
            text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(contents)).pages)
        elif suffix == ".docx":
            from io import BytesIO
            from docx import Document
            text = "\n".join(paragraph.text for paragraph in Document(BytesIO(contents)).paragraphs)
        else:
            text = contents.decode("utf-8-sig")
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Could not extract text from this document") from exc
    text = text.strip()
    if len(text) < 20:
        raise HTTPException(status_code=422, detail="This document contains too little readable text")
    article = Article(title=Path(filename).stem[:240], summary=text[:450], content=text[:30000], category=category,
                      tags="uploaded, document", source=filename, created_by=user.id)
    db.add(article)
    await index_article(db, article)
    db.commit()
    db.refresh(article)
    return article_view(article)


@app.get("/api/tickets")
def list_tickets(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    statement = select(Ticket).options(joinedload(Ticket.owner)).order_by(Ticket.updated_at.desc())
    if user.role == "user":
        statement = statement.where(Ticket.owner_id == user.id)
    elif user.role == "agent":
        statement = statement.where((Ticket.assignee_id == user.id) | (Ticket.owner_id == user.id))
    return {"tickets": [ticket_view(ticket) for ticket in db.scalars(statement).unique().all()]}


@app.post("/api/tickets", status_code=201)
def create_ticket(payload: TicketInput, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    ticket = Ticket(ticket_key=f"NX-{secrets.token_hex(3).upper()}", owner_id=user.id,
                    subject=payload.subject.strip(), description=payload.description.strip(), priority=payload.priority)
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    ticket.owner = user
    return ticket_view(ticket)


@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    ticket = db.scalar(select(Ticket).options(joinedload(Ticket.owner), joinedload(Ticket.comments).joinedload(TicketComment.author)).where(Ticket.id == ticket_id))
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ensure_ticket_access(ticket, user)
    return ticket_view(ticket, include_comments=True)


@app.patch("/api/tickets/{ticket_id}")
def update_ticket(ticket_id: int, payload: TicketUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    ticket = db.scalar(select(Ticket).options(joinedload(Ticket.owner), joinedload(Ticket.comments).joinedload(TicketComment.author)).where(Ticket.id == ticket_id))
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ensure_ticket_access(ticket, user)
    if payload.status or "assignee_id" in payload.model_fields_set:
        if user.role not in {"admin", "agent"}:
            raise HTTPException(status_code=403, detail="Only support staff can update ticket status or assignment")
        if payload.status:
            ticket.status = payload.status
        if "assignee_id" in payload.model_fields_set and payload.assignee_id is None:
            ticket.assignee_id = None
        elif payload.assignee_id is not None:
            assignee = db.get(User, payload.assignee_id)
            if not assignee or assignee.role not in {"agent", "admin"}:
                raise HTTPException(status_code=422, detail="Assignee must be a support agent or admin")
            ticket.assignee_id = assignee.id
    if payload.comment and payload.comment.strip():
        ticket.comments.append(TicketComment(author_id=user.id, content=payload.comment.strip()))
    db.commit()
    db.refresh(ticket)
    return ticket_view(ticket, include_comments=True)


@app.post("/api/tickets/{ticket_id}/knowledge", status_code=201)
async def ticket_to_article(ticket_id: int, user: User = Depends(require_roles("admin", "agent")), db: Session = Depends(get_db)) -> dict:
    ticket = db.get(Ticket, ticket_id)
    if not ticket or ticket.status != "Resolved":
        raise HTTPException(status_code=409, detail="Resolve the ticket before adding it to the knowledge base")
    article = Article(title=ticket.subject, summary=ticket.description[:450], content=ticket.description,
                      category="Software", tags="resolved ticket", source=f"Support case {ticket.ticket_key}", created_by=user.id)
    db.add(article)
    await index_article(db, article)
    db.commit()
    db.refresh(article)
    return article_view(article)


@app.post("/api/feedback", status_code=201)
def submit_feedback(payload: FeedbackInput, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if not db.get(Article, payload.article_id):
        raise HTTPException(status_code=404, detail="Article not found")
    existing = db.scalar(select(Feedback).where(Feedback.user_id == user.id, Feedback.article_id == payload.article_id))
    if existing:
        existing.helpful = payload.helpful
    else:
        db.add(Feedback(user_id=user.id, article_id=payload.article_id, helpful=payload.helpful))
    db.commit()
    return {"ok": True}


@app.get("/api/bookmarks")
def list_bookmarks(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    articles = db.scalars(select(Article).join(Bookmark).where(Bookmark.user_id == user.id).order_by(Bookmark.created_at.desc())).all()
    return {"articles": [article_view(article) for article in articles]}


@app.post("/api/bookmarks/{article_id}", status_code=201)
def add_bookmark(article_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    if not db.get(Article, article_id):
        raise HTTPException(status_code=404, detail="Article not found")
    existing = db.scalar(select(Bookmark).where(Bookmark.user_id == user.id, Bookmark.article_id == article_id))
    if not existing:
        db.add(Bookmark(user_id=user.id, article_id=article_id))
        db.commit()
    return {"ok": True}


@app.delete("/api/bookmarks/{article_id}", status_code=204)
def remove_bookmark(article_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)) -> None:
    bookmark = db.scalar(select(Bookmark).where(Bookmark.user_id == user.id, Bookmark.article_id == article_id))
    if bookmark:
        db.delete(bookmark)
        db.commit()


@app.get("/api/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    logs = db.scalars(select(SearchLog).where(SearchLog.user_id == user.id).order_by(SearchLog.created_at.desc()).limit(5)).all()
    ticket_query = select(Ticket).options(joinedload(Ticket.owner)).order_by(Ticket.updated_at.desc()).limit(4)
    if user.role == "user":
        ticket_query = ticket_query.where(Ticket.owner_id == user.id)
    elif user.role == "agent":
        ticket_query = ticket_query.where((Ticket.assignee_id == user.id) | (Ticket.owner_id == user.id))
    popular = db.execute(select(SearchLog.query, func.count(SearchLog.id).label("count")).group_by(SearchLog.query).order_by(func.count(SearchLog.id).desc()).limit(5)).all()
    return {
        "user": user_view(user),
        "recent_searches": [{"query": row.query, "created_at": row.created_at} for row in logs],
        "tickets": [ticket_view(item) for item in db.scalars(ticket_query).unique().all()],
        "popular": [{"query": row.query, "count": row.count} for row in popular],
        "categories": CATEGORIES,
        "stats": {"articles": db.scalar(select(func.count(Article.id))) or 0,
                   "open_tickets": db.scalar(select(func.count(Ticket.id)).where(Ticket.status.in_(["Open", "In Progress"]))) or 0,
                   "searches": db.scalar(select(func.count(SearchLog.id))) or 0},
    }


@app.get("/api/admin/stats")
def admin_stats(_user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)) -> dict:
    unresolved = db.scalars(select(Ticket).options(joinedload(Ticket.owner)).where(Ticket.status.in_(["Open", "In Progress"])).order_by(Ticket.created_at.desc()).limit(8)).unique().all()
    frequent = db.execute(select(SearchLog.query, func.count(SearchLog.id).label("count")).group_by(SearchLog.query).order_by(func.count(SearchLog.id).desc()).limit(8)).all()
    return {"users": db.scalar(select(func.count(User.id)) or 0),
            "articles": db.scalar(select(func.count(Article.id)) or 0),
            "unresolved": [ticket_view(ticket) for ticket in unresolved],
            "frequent": [{"query": row.query, "count": row.count} for row in frequent]}


@app.get("/api/agent/stats")
def agent_stats(user: User = Depends(require_roles("admin", "agent")), db: Session = Depends(get_db)) -> dict:
    statement = select(Ticket).options(joinedload(Ticket.owner)).where(Ticket.status.in_(["Open", "In Progress"]))
    if user.role == "agent":
        statement = statement.where(Ticket.assignee_id == user.id)
    unresolved = db.scalars(statement.order_by(Ticket.created_at.desc()).limit(8)).unique().all()
    assigned_count = db.scalar(select(func.count(Ticket.id)).where(Ticket.assignee_id == user.id)) or 0
    in_progress = db.scalar(select(func.count(Ticket.id)).where(Ticket.assignee_id == user.id, Ticket.status == "In Progress")) or 0
    frequent = db.execute(select(SearchLog.query, func.count(SearchLog.id).label("count")).group_by(SearchLog.query).order_by(func.count(SearchLog.id).desc()).limit(8)).all()
    return {"assigned": assigned_count, "in_progress": in_progress,
            "articles": db.scalar(select(func.count(Article.id))) or 0,
            "unresolved": [ticket_view(ticket) for ticket in unresolved],
            "frequent": [{"query": row.query, "count": row.count} for row in frequent]}


@app.get("/api/admin/users")
def admin_users(_user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)) -> dict:
    return {"users": [user_view(user) for user in db.scalars(select(User).order_by(User.created_at.desc())).all()]}


@app.patch("/api/admin/users/{user_id}/role")
def change_role(user_id: int, payload: RoleUpdate, user: User = Depends(require_roles("admin")), db: Session = Depends(get_db)) -> dict:
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == target.id and payload.role != "admin":
        raise HTTPException(status_code=409, detail="You cannot remove your own admin role")
    target.role = payload.role
    db.commit()
    return user_view(target)


@app.get("/api/search/history")
def search_history(user: User = Depends(current_user), db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(select(SearchLog).where(SearchLog.user_id == user.id).order_by(SearchLog.created_at.desc()).limit(20)).all()
    return {"searches": [{"query": row.query, "created_at": row.created_at, "results_count": row.results_count} for row in rows]}


@app.get("/{requested_path:path}", include_in_schema=False)
def frontend(requested_path: str):
    if requested_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(BASE_DIR / "static" / "index.html")
