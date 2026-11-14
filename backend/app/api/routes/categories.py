from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_owner
from app.db.session import get_db
from app.models.category import Category
from app.models.user import User
from app.schemas.category import CategoryCreate, CategoryRead

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
async def list_categories(db: AsyncSession = Depends(get_db)) -> list[Category]:
    stmt = select(Category).order_by(Category.name)
    return list((await db.scalars(stmt)).all())


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_owner),
) -> Category:
    name = data.name.strip()
    existing = await db.scalar(select(Category).where(Category.name == name))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Такая категория уже существует",
        )
    category = Category(name=name)
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category
