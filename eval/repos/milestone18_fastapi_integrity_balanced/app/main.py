from fastapi import APIRouter, FastAPI
from pydantic import BaseModel

router = APIRouter()
app = FastAPI()


class NoteUpdate(BaseModel):
    content: str
    updated_at: str


@router.patch("/notes/{note_id}")
def update_note(note_id: str, payload: NoteUpdate) -> dict[str, bool]:
    client_updated_at = payload.updated_at
    db.execute(
        "UPDATE notes SET content = :content, updated_at = :updated_at "
        "WHERE user_id = :user_id AND id = :note_id AND updated_at = :previous_updated_at",
        {
            "content": payload.content,
            "updated_at": client_updated_at,
            "user_id": "demo",
            "note_id": note_id,
            "previous_updated_at": client_updated_at,
        },
    )
    return {"ok": True}


app.include_router(router)
