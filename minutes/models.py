import uuid

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base

from minutes.schemas import TaskStage

Base = declarative_base()

# Dummy owner id to use until user management is implemented
DUMMY_OWNER_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")


class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, server_default="false")
    email = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class Task(Base):
    __tablename__ = "tasks"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # short display name for the task (e.g. "Meeting: Engineering sync")
    name = Column(String, nullable=True, index=True)
    status = Column(
        SAEnum(
            TaskStage,
            name="task_stage",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            length=32,
        ),
        nullable=False,
        index=True,
    )
    progress = Column(Numeric, default=0)
    result = Column(JSON, nullable=True)
    fail_count = Column(Integer, default=0)
    last_failure_ts = Column(DateTime, nullable=True)
    last_success_ts = Column(DateTime, nullable=True)
    # Soft-delete flag and timestamp
    deleted = Column(Boolean, nullable=False, server_default="false")
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    schema_version = Column(Integer, default=1)


class TaskHistory(Base):
    __tablename__ = "task_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(
        UUID(as_uuid=True), ForeignKey("tasks.id"), nullable=False, index=True
    )
    event_ts = Column(DateTime, server_default=func.now())
    event_type = Column(String, nullable=True)
    payload = Column(JSON, nullable=True)


class Bucket(Base):
    __tablename__ = "buckets"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, unique=True, nullable=False, index=True)
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        default=DUMMY_OWNER_ID,
    )
    public = Column(Boolean, nullable=False, server_default="false")
    bucket_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    deleted_at = Column(DateTime, nullable=True)


class ServiceToken(Base):
    __tablename__ = "service_tokens"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=True)
    token_hash = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    revoked = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(DateTime, server_default=func.now())
