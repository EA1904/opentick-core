from app.db.session import Base
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, default="Default Account")
    balance = Column(Float, default=100000.0)
    margin = Column(Float, default=0.0)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User")
    trades = relationship(
        "Trade", back_populates="account", cascade="all, delete-orphan"
    )


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False, index=True)
    direction = Column(String, nullable=False)  # "BUY" or "SELL"
    price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    execution_type = Column(String, default="MARKET")  # "MARKET", "LIMIT", "STOP"
    status = Column(String, default="COMPLETED")  # "COMPLETED", "WORKING", "CANCELLED"
    pnl = Column(Float, default=0.0)  # Realized PnL if this trade closes a position
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)

    account = relationship("Account", back_populates="trades")
