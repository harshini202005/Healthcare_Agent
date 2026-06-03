# Healthcare Assistant Platform 

An intelligent, agent-driven healthcare platform that leverages **Mistral AI** and **Supabase** to provide automated appointment scheduling, medical knowledge retrieval via RAG, and clinical workflow automation.

##  Key Features

- **Agentic Chat Interface**: A conversational AI powered by Mistral AI that uses function-calling (MCP tools) to interact with medical data.
- **RAG (Retrieval-Augmented Generation)**: Uses `pgvector` similarity search to provide grounded answers based on a private medical knowledge base.
- **Appointment Management**: Automated booking engine with real-time conflict detection and doctor schedule management.
- **Workflow Automation**: Trigger-based engine for automated notifications (via Resend) and background task execution.
- **Real-time Updates**: FastAPI-powered Server-Sent Events (SSE) for seamless chat streaming and notification polling.

##  Tech Stack

- **Backend**: FastAPI (Python)
- **AI/LLM**: Mistral AI (Large 2 & Embeddings)
- **Database**: Supabase (PostgreSQL + `pgvector`)
- **Frontend**: Single-Page Application (HTML/JS)
- **Security**: Supabase RLS (Row Level Security) and IAM schemas
- **Communication**: Resend API for email notifications

##  Project Structure

```text
├── backend/
│   ├── agent/            # Mistral orchestrator and tool registry
│   ├── rag/              # Ingestion, embedding, and retrieval logic
│   ├── tools/            # Appointment booking and knowledge tools
│   ├── workflows/        # Automation engine and schedulers
│   └── database.py       # Supabase client and CRUD operations
├── frontend/             # SPA for chat and admin dashboards
├── supabase_schema.sql   # Core DDL for healthcare tables and vector search
├── main.py               # FastAPI application entry point
├── seed_database.py      # Utility to populate initial doctor/schedule data
└── requirements.txt      # Project dependencies
 ```

## Setup Instructions
1. Prerequisites
Python 3.9+
A Supabase project with pgvector enabled
API Keys for Mistral AI and Resend
2. Installation
Clone the repository and install dependencies:
git clone https://github.com/harshini202005/healthcare_agent.git
cd healthcare_agent
python -m venv .venv
source .venv/bin/activate  # Or `.venv\Scripts\activate` on Windows
pip install -r requirements.txt
3. Environment Configuration
Create a .env file based on .env.example:
MISTRAL_API_KEY=your_mistral_key
SUPABASE_URL=your_project_url
SUPABASE_KEY=your_service_role_key
RESEND_API_KEY=your_resend_key
4. Database Setup
Run the contents of supabase_schema.sql and supabase_iam_schema.sql in your Supabase SQL Editor.
Populate the initial data:
5. Running the Application
Start the FastAPI server:
bash run.sh
The application will be available at https://healthcare-agent-4o1k.onrender.com/.

## Security
This project uses Supabase IAM and Row Level Security to ensure patient data privacy. Sensitive keys are managed via environment variables and are excluded from version control via .gitignore.