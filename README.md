\# CareerCopilot-DevOps



\## Overview

CareerCopilot-DevOps is a DevOps implementation of the CareerCopilot AI full-stack application. It brings together a React frontend and FastAPI backend with supporting services, using Docker for containerization and preparing for GitHub and Jenkins CI/CD automation.



\## Technology Stack

\- \*\*Frontend:\*\* React, TypeScript, Vite, Nginx

\- \*\*Backend:\*\* Python, FastAPI, SQLAlchemy

\- \*\*Database:\*\* MySQL

\- \*\*Caching:\*\* Redis

\- \*\*AI workflow:\*\* LangGraph and retrieval-augmented generation (RAG)

\- \*\*Containerization:\*\* Docker and Docker Compose

\- \*\*Version control:\*\* Git and GitHub

\- \*\*CI/CD:\*\* Jenkins (planned)



\## Repository Structure

\- `frontend/careercopilot-frontend/` — frontend application and Docker configuration

\- `backend/careercopilot-backend/` — backend application, tests, and Docker configuration



\## Local Access

When the services are running locally:

\- Frontend: http://localhost:3000

\- Backend API: http://localhost:8000

\- API documentation: http://localhost:8000/docs



\## Current Status

\- Frontend and backend containerized

\- MySQL and Redis configured in Docker

\- Local application tested

\- GitHub repository preparation in progress

\- Jenkins CI/CD pipeline planned



\## Security

Do not commit environment files, API keys, passwords, uploaded user documents, or generated database/vector-store data. Use local environment configuration for secrets.



\## Note

This repository is maintained separately from the original CareerCopilot AI repository to support DevOps development and CI/CD experimentation.



