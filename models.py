from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from extensions import db


class User(db.Model):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(db.String(80), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(db.String(120), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    orders: Mapped[list["Order"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    favorites: Mapped[list["FavoriteMeal"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    shared_meals: Mapped[list["SharedMeal"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Order(db.Model):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(db.String(32), default="Pending", nullable=False)
    pickup_at: Mapped[datetime | None] = mapped_column(nullable=True)
    total_cents: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderItem(db.Model):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(db.String(128), nullable=False)
    item_name: Mapped[str] = mapped_column(db.String(255), nullable=False)
    unit_price_cents: Mapped[int] = mapped_column(nullable=False)
    quantity: Mapped[int] = mapped_column(default=1, nullable=False)

    order: Mapped["Order"] = relationship(back_populates="items")


class FavoriteMeal(db.Model):
    __tablename__ = "favorite_meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(db.String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="favorites")


class SharedMeal(db.Model):
    __tablename__ = "shared_meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(db.String(128), nullable=False)
    caption: Mapped[str] = mapped_column(db.String(280), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="shared_meals")
