# ct200-ai-qa-pipeline
AI-powered PDF document extraction and QA testing pipeline with FastAPI, SQLAlchemy, document versioning, traceability checks, and structured test case generation.
# CT200 AI QA Pipeline

A document-processing and quality assurance pipeline designed to extract structured information from PDF manuals, track document versions, manage selected requirements, generate structured QA test cases, and identify potentially outdated test cases when documents change.

## Key Features
- PDF text extraction with hierarchical document structure
- REST API built with FastAPI and Pydantic
- SQLAlchemy-based data persistence with SQLite
- Document version tracking and requirement selection
- Structured QA test case generation
- Traceability checks for detecting stale test cases
- Automated tests for core functionality

## Tech Stack
Python, FastAPI, Pydantic, SQLAlchemy, SQLite, PyMuPDF, Pytest

## Objective
To improve document-based QA workflows by connecting extracted requirements to structured test cases and tracking their validity across document versions.
