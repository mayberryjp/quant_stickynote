# Contributing to Quant Sticky Note

Thank you for contributing to the Quant Sticky Note project! This guide will help you understand our development process, code standards, and how to submit pull requests.

## Development Environment Setup

### Prerequisites
- Python 3.12 or later
- PostgreSQL 13 or later
- Docker & docker-compose (optional, for containerized testing)
- Git

### Initial Setup
```bash
# Clone the repository
git clone https://github.com/mayberryjp/quant_stickynote.git
cd quant_stickynote

# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install development dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Set up PostgreSQL (choose one option)
# Option A: Docker
docker-compose up -d

# Option B: Manual PostgreSQL
createdb quant_stickynote
export DATABASE_URL="postgresql://user:password@localhost:5432/quant_stickynote"

# Initialize database
alembic upgrade head

# Run tests to verify setup
pytest
```

## Code Style & Standards

### Python Standards
We follow these standards across the project:

1. **PEP 8** - Python Enhancement Proposal 8 (style guide)
2. **Type Hints** - All public function signatures must include type hints
   ```python
   def get_sticky_notes(limit: int, offset: int) -> list[StickyNote]:
       pass
   ```

3. **Docstrings** - Google-style docstrings for all modules, classes, and functions
   ```python
   def execute_query(query_def: QueryDefinition) -> list[Signal]:
       """Execute a query definition against external database.
       
       Args:
           query_def: The query definition to execute.
           
       Returns:
           List of signals extracted from query results.
           
       Raises:
           DatabaseConnectionError: If unable to connect to external DB.
           QueryExecutionError: If query fails or times out.
       """
   ```

4. **Imports** - Organized in three groups:
   ```python
   # 1. Standard library
   import os
   import logging
   from typing import Optional
   
   # 2. Third-party libraries
   from sqlalchemy import create_engine
   from pydantic import BaseSettings
   
   # 3. Local imports
   from quant_stickynote.models import StickyNote
   from quant_stickynote.exceptions import ConfigurationError
   ```

5. **Naming Conventions**:
   - Classes: `PascalCase` (e.g., `QueryEngine`, `StickyNote`)
   - Functions/methods: `snake_case` (e.g., `execute_query`, `get_signals`)
   - Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_TIMEOUT`, `MAX_POOL_SIZE`)
   - Private methods: `_snake_case` (e.g., `_validate_config`)

### Formatting Tools

Run these before committing:

```bash
# Black - Code formatter (enforce consistent style)
black src/ tests/

# isort - Import sorting
isort src/ tests/

# flake8 - Linting (check for style violations)
flake8 src/ tests/ --max-line-length=100

# All together
make lint
```

### Line Length
Maximum 100 characters per line (configured in `.flake8`).

## Database Migrations

**Always use Alembic for schema changes. Never modify tables directly.**

### Creating a Migration

1. Make changes to your SQLAlchemy models in `src/quant_stickynote/models.py`
2. Create auto-generated migration:
   ```bash
   alembic revision --autogenerate -m "Add new_column to sticky_notes"
   ```
3. Review the generated migration file in `alembic/versions/`
4. Test locally:
   ```bash
   # Create test database
   createdb quant_stickynote_test
   export DATABASE_URL="postgresql://user:password@localhost:5432/quant_stickynote_test"
   
   # Run migration
   alembic upgrade head
   
   # Verify schema
   psql quant_stickynote_test -c "\dt"
   ```
5. Include migration file with your PR
6. Document any manual SQL changes in the migration file comments

### Migration Best Practices
- Keep migrations small and focused
- Add descriptive messages: `alembic revision -m "Add status column and UNIQUE constraint"`
- Test both upgrade and downgrade: `alembic downgrade -1 && alembic upgrade head`
- Never modify migration files after merging to main
- Include rollback/downgrade instructions in PR description

## Testing

### Writing Tests

All tests should be in `tests/` directory organized as:
- `tests/unit/` - Unit tests (mocked dependencies)
- `tests/integration/` - Integration tests (real database)

Example test:
```python
import pytest
from quant_stickynote.query_engine import QueryEngine
from tests.fixtures import mock_external_db_result


def test_execute_query_extracts_signals(mock_external_db_result):
    """Test that QueryEngine correctly extracts signals from query results."""
    engine = QueryEngine()
    query_def = {
        "id": "test_query",
        "source_query": "SELECT * FROM test_table",
        "signal_extraction": {
            "symbol_column": "symbol",
            "buy_price_column": "price"
        }
    }
    
    # Act
    signals = engine.extract_signals(mock_external_db_result, query_def)
    
    # Assert
    assert len(signals) == 3
    assert signals[0].symbol == "AAPL"
    assert signals[0].buy_price == 150.25


def test_execute_query_handles_connection_error(mock_db_connection_error):
    """Test that QueryEngine raises DatabaseConnectionError on connection failure."""
    engine = QueryEngine()
    
    with pytest.raises(DatabaseConnectionError):
        engine.execute_external_query("postgresql://invalid", "SELECT 1")
```

### Running Tests

```bash
# All tests
pytest

# With coverage report
pytest --cov=src/quant_stickynote --cov-report=html

# Specific test file
pytest tests/unit/test_query_engine.py -v

# Specific test function
pytest tests/unit/test_query_engine.py::test_execute_query_extracts_signals -v

# Watch mode (requires pytest-watch)
ptw

# Stop on first failure (useful during debugging)
pytest -x
```

### Test Coverage Requirements

- Minimum **80% code coverage** required for all PRs
- Critical paths (signal extraction, dedup, error handling) should have **>90% coverage**
- View coverage report: `pytest --cov=src/quant_stickynote --cov-report=html` then open `htmlcov/index.html`

### Mocking External Dependencies

Always mock external databases and APIs in unit tests:

```python
from unittest.mock import Mock, patch

@patch('quant_stickynote.query_engine.psycopg.connect')
def test_query_with_mock_database(mock_connect):
    """Example of mocking an external database connection."""
    mock_connection = Mock()
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = [
        ('AAPL', 150.25),
        ('MSFT', 330.50)
    ]
    mock_connection.cursor.return_value = mock_cursor
    mock_connect.return_value = mock_connection
    
    # Now your code under test will use the mocked connection
    engine = QueryEngine()
    results = engine.execute_external_query("SELECT...", "test_url")
    
    mock_cursor.fetchall.assert_called_once()
```

## Git Workflow

### Branch Naming
- Feature: `feature/description` (e.g., `feature/add-email-notifications`)
- Bugfix: `bugfix/description` (e.g., `bugfix/fix-duplicate-signals`)
- Maintenance: `maint/description` (e.g., `maint/upgrade-dependencies`)

### Commit Messages
Follow conventional commits format:

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`

**Examples**:
```
feat(query-engine): add support for filtering expressions

Implement optional filter_expression in query definitions
to allow more flexible signal extraction without code changes.

Fixes #42
```

```
fix(worker): prevent duplicate query execution on restart

Add last_execution_time check to query_executions table
to prevent running same query twice within check interval.

Closes #35
```

### Pull Request Process

1. **Create feature branch**
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes and commit**
   ```bash
   git add .
   git commit -m "feat(scope): your commit message"
   ```

3. **Push and create PR**
   ```bash
   git push origin feature/your-feature-name
   ```

4. **PR Description** (required):
   ```markdown
   ## Description
   Brief summary of changes.
   
   ## Type of Change
   - [ ] Bug fix
   - [ ] New feature
   - [ ] Breaking change
   - [ ] Documentation update
   
   ## Testing
   - [ ] Unit tests added
   - [ ] Integration tests added
   - [ ] Manual testing completed
   - [ ] All tests passing (pytest --cov)
   
   ## Checklist
   - [ ] Code follows style guidelines (black, flake8)
   - [ ] Docstrings added/updated
   - [ ] Type hints included
   - [ ] No hardcoded values (use config)
   - [ ] Database migrations included (if applicable)
   - [ ] Documentation updated
   - [ ] No unrelated changes
   
   ## Related Issues
   Closes #123
   
   ## Notes for Reviewers
   Any special considerations or areas needing careful review.
   ```

5. **Code Review**
   - Respond to all feedback
   - Request re-review after changes
   - Resolve conversations when addressed

6. **Merge**
   - Use "Squash and merge" for feature branches
   - Use "Create a merge commit" for release branches
   - Delete branch after merging

## Adding New Query Definitions

Query definitions are JSON files in `queries/` directory. Use this process:

1. **Create JSON file** with meaningful name: `queries/my_signal_strategy.json`

2. **Follow the schema** (see `SPEC.md` Appendix for full schema)

3. **Include comments** for clarity:
   ```json
   {
     "id": "rsi_oversold_001",
     "name": "RSI Oversold Reversal",
     "description": "Identifies stocks with RSI < 30 and potential reversal patterns",
     "enabled": false,
     "external_database": {
       "url": "postgresql://user:pass@data-warehouse:5432/technical_analysis"
     },
     "source_query": "SELECT symbol, reversal_price FROM oversold_reversals WHERE rsi < 30 AND DATE(scan_date) = CURRENT_DATE",
     "signal_extraction": {
       "symbol_column": "symbol",
       "buy_price_column": "reversal_price",
       "trigger_reason_template": "RSI Oversold [RSI value below 30]"
     },
     "dedup_key_ttl_hours": 48
   }
   ```

4. **Test before enabling**:
   - Set `"enabled": false` initially
   - Test with API: `GET /queries` to verify it loads
   - Manually test query against external DB
   - Check signal extraction with sample data
   - Set `"enabled": true` when confident

5. **Document in PR**: Explain what this query looks for and why

## Documentation

### README and API Docs
- Keep [README.md](README.md) updated with API changes
- Document all new environment variables
- Add examples for new endpoints

### Code Comments
- Explain the "why", not the "what"
- Comments for complex logic or non-obvious choices
- Keep comments up to date with code changes

Example:
```python
# BAD - Explains what the code does (obvious)
x = y + 1  # Add 1 to y

# GOOD - Explains why this logic exists
# Offset by 1 because database indices start at 0 but user-facing IDs start at 1
item_id = db_index + 1
```

### Docstrings
All public functions, classes, and modules need docstrings:

```python
"""Query execution engine for quant_stickynote.

This module handles loading query definitions, connecting to external databases,
executing SQL queries, and extracting trading signals from result sets.

Typical usage example:
    engine = QueryEngine()
    query_def = QueryDefinition.from_json("queries/my_signal.json")
    signals = engine.execute(query_def)
"""
```

## Performance Considerations

When making changes, consider:
- Does this add database queries? Use indexes where needed
- Does this increase memory usage? Check steady-state memory with large datasets
- Does this add latency to critical paths? Keep API responses <500ms
- Use pagination for large result sets
- Connection pooling for external databases

## Reporting Issues

### Bug Reports
Include:
1. Clear description of the problem
2. Steps to reproduce
3. Expected vs. actual behavior
4. Environment (OS, Python version, etc.)
5. Logs or error messages (sanitized)

### Feature Requests
Include:
1. Use case / motivation
2. Proposed solution (if any)
3. Alternative approaches considered
4. Any related issues

## Project Architecture

Understanding the project structure helps with contributions:

- **config.py**: Pydantic settings, all configuration
- **models.py**: SQLAlchemy ORM models, database schema
- **database.py**: Session management, connection pooling
- **query_engine.py**: Query loading, execution, signal extraction
- **signal_processor.py**: Deduplication, persistence
- **api.py**: Bottle app, REST endpoints
- **worker.py**: Main daemon loop, scheduling
- **logger.py**: Structured JSON logging

Read [SPEC.md](SPEC.md) for detailed architecture.

## Getting Help

- Check [SPEC.md](SPEC.md) and [README.md](README.md) first
- Review existing issues for similar problems
- Ask in PR comments or new issue
- Contact project maintainers for complex questions

## Code Review Guidelines

### Reviewing Others' Code
- Be respectful and constructive
- Suggest improvements rather than demand changes
- Approve if code is good enough (don't seek perfection)
- Test changes locally if possible

### Responding to Reviews
- Treat feedback as learning opportunity
- Ask for clarification if feedback is unclear
- Explain your reasoning for design choices
- Make requested changes promptly

## Release Process

(Managed by maintainers)

- Semantic versioning: `MAJOR.MINOR.PATCH`
- Changelog in [CHANGELOG.md](CHANGELOG.md)
- Tag releases in git
- Publish to PyPI

---

Thank you for contributing to making Quant Sticky Note better! 🙏
