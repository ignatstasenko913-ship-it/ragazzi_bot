from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey,
    Integer, String, Text, JSON, Index,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


# ── Enums ─────────────────────────────────────────────────────────────────────

class OrderSource(str, enum.Enum):
    SITE = "site"
    APP = "app"
    UNKNOWN = "unknown"


class OrderStatus(str, enum.Enum):
    PENDING = "pending"
    ROUTED = "routed"
    PROBLEMATIC = "problematic"
    DUPLICATE = "duplicate"
    PARSE_ERROR = "parse_error"
    MANUALLY_ROUTED = "manually_routed"
    CANCELLED = "cancelled"


class OrderType(str, enum.Enum):
    DELIVERY = "delivery"
    PICKUP = "pickup"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"


class ProblematicReason(str, enum.Enum):
    ADDRESS_NOT_FOUND = "address_not_found"
    ADDRESS_OUT_OF_ZONE = "address_out_of_zone"
    PARSE_ERROR = "parse_error"
    UNKNOWN_FORMAT = "unknown_format"
    NO_ACTIVE_BRANCHES = "no_active_branches"
    ROUTING_FAILED = "routing_failed"
    SUSPICIOUS_ADDRESS = "suspicious_address"


# ── Models ────────────────────────────────────────────────────────────────────

class Branch(Base):
    __tablename__ = "branches"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    short_name = Column(String(100), nullable=True)
    address = Column(String(500), nullable=False)
    lat = Column(Float, nullable=False)
    lon = Column(Float, nullable=False)
    telegram_group_id = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    last_order_sent_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    orders = relationship("Order", back_populates="branch")

    def __repr__(self) -> str:
        return f"<Branch {self.name!r} active={self.is_active}>"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    order_number = Column(String(100), nullable=True, index=True)
    source = Column(Enum(OrderSource), default=OrderSource.UNKNOWN, nullable=False)
    order_type = Column(Enum(OrderType), nullable=True)
    status = Column(Enum(OrderStatus), default=OrderStatus.PENDING, nullable=False)

    # Customer
    customer_name = Column(String(200), nullable=True)
    customer_phone = Column(String(50), nullable=True, index=True)

    # Address / pickup
    delivery_address = Column(String(500), nullable=True)
    delivery_lat = Column(Float, nullable=True)
    delivery_lon = Column(Float, nullable=True)
    pickup_branch_name = Column(String(200), nullable=True)
    address_validated = Column(Boolean, nullable=True)
    address_in_zone = Column(Boolean, nullable=True)

    # Order details
    items = Column(JSON, nullable=True)          # [{"name": ..., "qty": ..., "price": ...}]
    total_amount = Column(Float, nullable=True)
    discount = Column(Float, nullable=True)
    comment = Column(Text, nullable=True)
    payment_method = Column(String(100), nullable=True)
    payment_status = Column(String(100), nullable=True)
    delivery_time = Column(String(100), nullable=True)
    order_date = Column(String(50), nullable=True)

    # Texts
    raw_text = Column(Text, nullable=False)
    formatted_text = Column(Text, nullable=True)

    # Source metadata
    source_group_id = Column(String(100), nullable=True)
    source_message_id = Column(Integer, nullable=True, index=True)

    # Routing result
    branch_id = Column(Integer, ForeignKey("branches.id"), nullable=True)
    travel_time_minutes = Column(Integer, nullable=True)

    # Problem info
    problem_reason = Column(Enum(ProblematicReason), nullable=True)
    problem_detail = Column(Text, nullable=True)
    is_resolved = Column(Boolean, default=False, nullable=False)
    resolved_by_id = Column(Integer, ForeignKey("telegram_users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    routed_at = Column(DateTime, nullable=True)

    branch = relationship("Branch", back_populates="orders")
    resolved_by = relationship("TelegramUser", foreign_keys=[resolved_by_id])
    duplicates = relationship(
        "DuplicateOrder",
        foreign_keys="DuplicateOrder.order_id",
        back_populates="order",
    )

    __table_args__ = (
        Index("ix_orders_status_created", "status", "created_at"),
        Index("ix_orders_source_group_msg", "source_group_id", "source_message_id"),
    )

    def __repr__(self) -> str:
        return f"<Order #{self.order_number} status={self.status}>"


class DuplicateOrder(Base):
    __tablename__ = "duplicate_orders"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    original_order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    detected_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    notified = Column(Boolean, default=False, nullable=False)

    order = relationship("Order", foreign_keys=[order_id], back_populates="duplicates")
    original_order = relationship("Order", foreign_keys=[original_order_id])


class TelegramUser(Base):
    __tablename__ = "telegram_users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    full_name = Column(String(200), nullable=True)
    role = Column(Enum(UserRole), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ErrorLog(Base):
    __tablename__ = "error_logs"

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=True)
    error_type = Column(String(100), nullable=False)
    error_message = Column(Text, nullable=False)
    raw_text = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    resolved = Column(Boolean, default=False, nullable=False)

    order = relationship("Order", foreign_keys=[order_id])
