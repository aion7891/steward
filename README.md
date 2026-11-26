# Steward

Steward is a planned, local-first AI assistant that helps keep a computer
organized and makes it easier to understand how its files, applications, and
storage are being used.

## What it aims to do

- Inspect selected folders and common document types, and identify duplicates,
  large or stale files, and temporary files.
- Monitor Downloads and suggest useful destinations for new files.
- Answer questions about documents and recent work using local search and
  summaries.
- Recommend ways to organize files, archive older items, and reclaim disk
  space.
- Provide reports on storage, file categories, activity, and software usage.

Steward is intended to keep personal data on the user's computer. File changes
will be designed with safety in mind: destructive actions require confirmation,
support dry runs, move items to a recoverable location first, and record actions
for review.

## Planned approach

The project is planned in phases, starting with configuration and scanning,
then adding document search, a curated knowledge bundle, agent workflows,
organization actions, reports, a local chat interface, and Docker deployment.
The intended stack includes Python, Agno, SQLite, Ollama, a local vector store,
and an optional local web interface.

This repository currently contains the project overview and ignore rules; the
application is not implemented yet.
