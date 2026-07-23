# Genesis AI Context

> This document is the primary entry point for any AI assistant working on the Genesis project.
> Read this file before reading the source code.

---

# Project Overview

**Project Name:** Genesis

**Purpose:**
Genesis is an open-source Agent Operating System (Agent OS) for building scalable, modular, and autonomous AI applications.

The project aims to provide reusable infrastructure such as runtime management, memory, workflows, plugins, tools, configuration, logging, and other core services that AI applications can build upon.

Genesis Core must remain generic and reusable. It should never contain application-specific business logic.

---

# Current Project Status

Current Phase:
Backend Foundation

Completed:

- FastAPI backend setup
- Project structure
- Configuration management
- Logging system
- Initial database foundation
- Development workflow established
- Git repository initialized
- GitHub repository created

Current Milestone:

Backend Infrastructure Complete

---

# Architecture Philosophy

Genesis follows a modular architecture.

Major principles:

- Keep modules loosely coupled.
- Prefer composition over tight coupling.
- Build reusable infrastructure before applications.
- Keep Genesis Core application-agnostic.
- Every module should have a single responsibility.

---

# Current Development Goal

Immediate Goal:

Build the backend infrastructure incrementally according to the frozen architecture.

Current Focus:

Continue implementing backend core components one milestone at a time.

---

# Important Decisions

This section records architectural decisions that future AI assistants must know.

Current decisions:

- Architecture is frozen before implementation.
- Genesis Core must remain application-agnostic.
- Development happens milestone by milestone.
- Each milestone is committed to Git after completion.
- Terminal commands are executed one step at a time.

---

# AI Working Guidelines

When working on Genesis:

1. Read this file first.
2. Read only the files relevant to the current task.
3. Avoid unnecessary architectural changes.
4. Follow existing coding conventions.
5. Preserve modularity.
6. If a requested change affects architecture, explain the impact before implementing it.

---

# Last Updated

Backend Foundation Milestone