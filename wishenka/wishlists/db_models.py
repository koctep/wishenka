"""SQLAlchemy 2.0 declarative database models for wishlists."""

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from wishenka.currency import DEFAULT_CURRENCY


class Base(DeclarativeBase):
    """Base declarative class for wishlist database models."""


class UserRefRow(Base):
    """Minimal declarative reference to the users profile table for FK metadata."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)


class WishlistRow(Base):
    """Relational row for the wishlist aggregate root."""

    __tablename__ = "wl_lists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    owner_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    event_title: Mapped[str | None] = mapped_column(String, nullable=True)
    event_date: Mapped[str | None] = mapped_column(String, nullable=True)
    is_collaborative: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warn_on_delete_reserved: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)
    public_token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    invite_token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    invite_token_expires_at: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    members: Mapped[list["WishlistMemberRow"]] = relationship(
        back_populates="wishlist", cascade="all, delete-orphan"
    )
    items: Mapped[list["WishItemRow"]] = relationship(
        back_populates="wishlist", cascade="all, delete-orphan"
    )


class WishlistMemberRow(Base):
    """Relational row for collaborative wishlist members."""

    __tablename__ = "wl_members"
    __table_args__ = (UniqueConstraint("wishlist_id", "user_id", name="idx_wl_members_unique"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wishlist_id: Mapped[int] = mapped_column(
        ForeignKey("wl_lists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String, nullable=False, default="member")
    joined_at: Mapped[str] = mapped_column(String, nullable=False)

    wishlist: Mapped["WishlistRow"] = relationship(back_populates="members")


class WishItemRow(Base):
    """Relational row for individual items within a wishlist."""

    __tablename__ = "wl_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wishlist_id: Mapped[int] = mapped_column(
        ForeignKey("wl_lists.id", ondelete="CASCADE"), nullable=False, index=True
    )
    recipient_user_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    recipient_name: Mapped[str | None] = mapped_column(String, nullable=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    link: Mapped[str | None] = mapped_column(String, nullable=True)
    price: Mapped[int | float | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String, nullable=False, default=DEFAULT_CURRENCY)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    received_quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    store_name: Mapped[str | None] = mapped_column(String, nullable=True)
    store_icon_url: Mapped[str | None] = mapped_column(String, nullable=True)
    priority: Mapped[str] = mapped_column(String, nullable=False, default="medium")
    category: Mapped[str | None] = mapped_column(String, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    is_archived: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    wishlist: Mapped["WishlistRow"] = relationship(back_populates="items")
    reservations: Mapped[list["ReservationRow"]] = relationship(
        back_populates="wish_item", cascade="all, delete-orphan"
    )


class ReservationRow(Base):
    """Relational row for item reservation records."""

    __tablename__ = "wl_reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    wish_item_id: Mapped[int] = mapped_column(
        ForeignKey("wl_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String, nullable=False, default="active", index=True)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)

    wish_item: Mapped["WishItemRow"] = relationship(back_populates="reservations")


class WishlistFavoriteRow(Base):
    """Relational row for user wishlist favorites."""

    __tablename__ = "wl_favorites"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.telegram_id", ondelete="CASCADE"), primary_key=True
    )
    wishlist_id: Mapped[int] = mapped_column(
        ForeignKey("wl_lists.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[str] = mapped_column(String, nullable=False)


class ViewHistoryRow(Base):
    """Relational row for user viewing history entries."""

    __tablename__ = "wl_view_history"
    __table_args__ = (UniqueConstraint("user_id", "wishlist_id", name="wl_view_history_user_wl"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.telegram_id", ondelete="CASCADE"), nullable=False, index=True
    )
    wishlist_id: Mapped[int] = mapped_column(
        ForeignKey("wl_lists.id", ondelete="CASCADE"), nullable=False
    )
    viewed_at: Mapped[str] = mapped_column(String, nullable=False)


class WishlistTokenRow(Base):
    """Relational row for active and historical public access capability tokens."""

    __tablename__ = "wl_tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True)
    wishlist_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    active: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class InviteTokenRow(Base):
    """Relational row for collaborator invite capability tokens."""

    __tablename__ = "wl_invite_tokens"

    token: Mapped[str] = mapped_column(String, primary_key=True)


class CounterRow(Base):
    """Relational row for monotonic entity identifier sequences."""

    __tablename__ = "wl_counters"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[int] = mapped_column(Integer, nullable=False)
