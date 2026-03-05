from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from database import Base
from datetime import datetime


class Lock(Base):
    __tablename__ = "locks"

    id = Column(Integer, primary_key=True, index=True)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    status = Column(String, default="inactive")
    last_update = Column(DateTime, default=datetime.now)

    # Relationships
    events = relationship("SecurityEvent", back_populates="lock")
    assignments = relationship("LockAssignment", back_populates="lock")

    @property
    def current_shipment(self):
        # Returns the active shipment assignment or None
        active = [a for a in self.assignments if a.released_at is None]
        return active[0].shipment if active else None


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id = Column(Integer, primary_key=True, index=True)
    lock_id = Column(Integer, ForeignKey("locks.id"), nullable=False)
    event_type = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    event_time = Column(DateTime, default=datetime.now)

    # Relationship
    lock = relationship("Lock", back_populates="events")


class Shipment(Base):
    __tablename__ = "shipments"

    id = Column(Integer, primary_key=True, index=True)
    shipment_id = Column(String, unique=True, nullable=False)
    status = Column(String, default="in_transit")

    # Relationship
    assignments = relationship("LockAssignment", back_populates="shipment")

    @property
    def active_locks(self):
        # Returns only locks currently assigned to this shipment
        return [a.lock for a in self.assignments if a.released_at is None]


class LockAssignment(Base):
    __tablename__ = "lock_assignments"

    id = Column(Integer, primary_key=True, index=True)
    lock_id = Column(Integer, ForeignKey("locks.id"), nullable=False)
    shipment_id = Column(Integer, ForeignKey("shipments.id"), nullable=False)
    assigned_at = Column(DateTime, default=datetime.now)
    released_at = Column(DateTime, nullable=True)  # null means currently assigned

    # Relationships
    lock = relationship("Lock", back_populates="assignments")
    shipment = relationship("Shipment", back_populates="assignments")