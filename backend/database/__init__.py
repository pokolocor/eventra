"""Persistence layer.

Eventra ships with two interchangeable stores behind one interface:

* `SqlRepository`   - SQLAlchemy + PostgreSQL (production; `DATABASE_URL`).
* `JsonFileRepository` - a zero-dependency file store used for Demo Mode and
  for running the project with no database installed at all.

`create_repository()` picks the right one from configuration.
"""

from backend.database.repository import (
    JsonFileRepository,
    Repository,
    SqlRepository,
    create_repository,
)

__all__ = ["JsonFileRepository", "Repository", "SqlRepository", "create_repository"]
