"""Test configuration for Phase 3 backend tests.

Uses a file-based SQLite test database via dependency override,
never touching the production PostgreSQL database.
"""

import os
import tempfile
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import SessionLocal as ProdSessionLocal  # noqa: F401
from app.main import app
from app.dependencies import get_db
from app.models.user import Base
from app.models.document import Document, Chunk  # noqa: F401

# Create a temporary SQLite test database
test_db_fd, test_db_path = tempfile.mkstemp(suffix=".sqlite3")
os.close(test_db_fd)
TEST_DATABASE_URL = f"sqlite:///{test_db_path}"

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

test_engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db() -> Generator[Session, None, None]:
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables in the test database before tests run."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    try:
        os.remove(test_db_path)
    except FileNotFoundError:
        pass


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """Provide a test database session."""
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient."""
    with TestClient(app) as c:
        yield c
