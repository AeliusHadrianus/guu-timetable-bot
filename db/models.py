from sqlalchemy.orm import declarative_base, relationship, Mapped, mapped_column
from sqlalchemy import Integer, String, Date, Time, DateTime, ForeignKey, Boolean, UniqueConstraint
from datetime import datetime

Base = declarative_base()

class Faculty(Base):
    __tablename__ = "faculty"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    short_name: Mapped[str] = mapped_column(String, unique=True)
    full_name: Mapped[str] = mapped_column(String, nullable=True)

class Group(Base):
    __tablename__ = "group"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    faculty_id: Mapped[int] = mapped_column(ForeignKey("faculty.id", ondelete="CASCADE"))
    code: Mapped[str] = mapped_column(String)
    course: Mapped[int] = mapped_column(Integer)
    faculty = relationship("Faculty", backref="groups")
    __table_args__ = (UniqueConstraint("faculty_id", "code"),)

class Teacher(Base):
    __tablename__ = "teacher"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True)

class Room(Base):
    __tablename__ = "room"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    building: Mapped[str] = mapped_column(String)
    number: Mapped[str] = mapped_column(String)
    __table_args__ = (UniqueConstraint("building", "number"),)

class SourceFile(Base):
    __tablename__ = "source_file"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String, unique=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    semester: Mapped[str] = mapped_column(String, nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Lesson(Base):
    __tablename__ = "lesson"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id", ondelete="CASCADE"))
    date: Mapped[Date] = mapped_column(Date)
    start_time: Mapped[Time] = mapped_column(Time)
    end_time: Mapped[Time] = mapped_column(Time)
    subject: Mapped[str] = mapped_column(String)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teacher.id"), nullable=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id"), nullable=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("source_file.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class User(Base):
    __tablename__ = "user"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)  # Telegram ID
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class UserGroup(Base):
    __tablename__ = "user_group"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("user.id", ondelete="CASCADE"))
    group_id: Mapped[int] = mapped_column(ForeignKey("group.id"))
    selected_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("user_id", "is_active"),)
