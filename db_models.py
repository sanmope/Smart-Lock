import uuid
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


def _uuid():
    return str(uuid.uuid4())


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lock_id = Column(String, ForeignKey("locks.id"), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    lock = relationship("Lock", back_populates="location")


class Lock(Base):
    __tablename__ = "locks"

    id = Column(String, primary_key=True, default=_uuid)
    status = Column(String, default="inactive")
    last_update = Column(DateTime, default=datetime.utcnow)

    location = relationship("Location", back_populates="lock", uselist=False)
    events = relationship("SecurityEvent", back_populates="lock")
    assignments = relationship("LockAssignment", back_populates="lock")

    @property
    def current_shipment(self):
        active = [a for a in self.assignments if a.released_at is None]
        return active[0].shipment if active else None


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id = Column(String, primary_key=True, default=_uuid)
    lock_id = Column(String, ForeignKey("locks.id"), nullable=False)
    event_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    event_time = Column(DateTime, default=datetime.utcnow)

    lock = relationship("Lock", back_populates="events")


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    shipment_id = Column(String, unique=True, nullable=False)
    status = Column(String, default="in_transit")
    last_update = Column(DateTime, default=datetime.utcnow)

    assignments = relationship("LockAssignment", back_populates="shipment")

    @property
    def active_locks(self):
        return [a.lock for a in self.assignments if a.released_at is None]


class LockAssignment(Base):
    __tablename__ = "lock_assignments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lock_id = Column(String, ForeignKey("locks.id"), nullable=False)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.utcnow)
    released_at = Column(DateTime, nullable=True)

    lock = relationship("Lock", back_populates="assignments")
    shipment = relationship("Shipment", back_populates="assignments")
