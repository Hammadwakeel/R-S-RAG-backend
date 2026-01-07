# Advanced RAG AI Backend with FastAPI & LangGraph

![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-0.109-009688.svg)
![Supabase](https://img.shields.io/badge/Supabase-PostgreSQL-3ECF8E.svg)
![Groq](https://img.shields.io/badge/Groq-LPU_Inference-orange.svg)
![LangGraph](https://img.shields.io/badge/LangGraph-Orchestration-black.svg)

> **Author:** [Hammad Wakeel](https://github.com/hammadwakeel)  
> A production-ready, high-performance conversational AI backend featuring **Server-Sent Events (SSE) Streaming**, **Smart Context Window Management**, and **Linear History Editing**.

---

## Overview

This backend powers a sophisticated ChatGPT-like application specialized for Technical Manual RAG (Retrieval Augmented Generation). Unlike standard chatbots, it solves the "Context Window" problem using a **Rolling Summary Architecture** and utilizes **Groq's LPU** for near-instant inference.

It is built with **FastAPI** for high concurrency and uses **Supabase** for secure authentication and persistent history.

### Key Features

* **⚡ Ultra-Fast Inference:** Powered by **Groq** (Llama-3/Mixtral) for sub-second token generation.
* **Real-Time Streaming:** Full SSE (Server-Sent Events) support for a typewriter-style UI experience.
* **Smart Context Memory:**
    * Automatically detects when chat history exceeds limits.
    * Compresses old messages into a "Long-Term Summary" using a lightweight LLM.
    * Preserves critical facts while freeing up token space.
* **Branching History (Edit & Regenerate):** Allows users to edit past messages. The system intelligently "rewinds" the chat timeline, deletes future contexts, and regenerates the response.
* **Advanced RAG Pipeline:**
    * **Voyage AI** for state-of-the-art embeddings.
    * **Qdrant** for vector similarity search.
    * **Local Deduplication** to remove repetitive context chunks.
* **Production Security:** JWT Authentication via Supabase Auth + Row Level Security (RLS).

---

## Tech Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **API Framework** | **FastAPI** | Async Python web server. |
| **Database** | **Supabase (PostgreSQL)** | Stores Users, Chats, Messages, and Summaries. |
| **Vector DB** | **Qdrant** | High-performance vector search engine. |
| **LLM Orchestration** | **LangGraph** | Graph-based state machine for RAG workflows. |
| **Inference Engine** | **Groq** | Running `openai/gpt-oss-120b` and `llama-4-scout`. |
| **Embeddings** | **Voyage AI** | specialized RAG embedding models. |

---

## Getting Started

### 1. Prerequisites
* Python 3.10+
* A Supabase Project
* API Keys for Groq, Voyage AI, and Qdrant.

### 2. Installation

```bash
# Clone the repository
git clone [https://github.com/Hammadwakeel/R-S-RAG-backend.git](hhttps://github.com/Hammadwakeel/R-S-RAG-backend.git)
cd R-S-RAG-backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

```

### 3. Environment Setup

Copy the example file and fill in your credentials:

```bash
cp .env.example .env

```

### 4. Database Setup (Supabase SQL)

Run the following SQL in your Supabase SQL Editor to set up the required tables and security policies:

```sql
-- 1. Create Profiles (Synced with Auth)
create table public.profiles (
  id uuid references auth.users on delete cascade primary key,
  email text,
  full_name text
);

-- 2. Create Chats with Summary Support
create table public.chats (
  id uuid default gen_random_uuid() primary key,
  user_id uuid references public.profiles(id),
  title text,
  summary text default '',  -- Crucial for Smart Memory
  created_at timestamp with time zone default timezone('utc'::text, now())
);

-- 3. Create Messages with Summary Flag
create table public.messages (
  id uuid default gen_random_uuid() primary key,
  chat_id uuid references public.chats(id) on delete cascade,
  role text,
  content text,
  is_summarized boolean default false, -- Crucial for Rolling Window
  created_at timestamp with time zone default timezone('utc'::text, now())
);

-- 4. Enable RLS (Security)
alter table public.chats enable row level security;
alter table public.messages enable row level security;

create policy "Users manage own chats" on chats for all using (auth.uid() = user_id);
create policy "Users manage own messages" on messages for all using (
  exists (select 1 from chats where id = messages.chat_id and user_id = auth.uid())
);

```

### 5. Running the Server

```bash
uvicorn app.main:app --reload

```

The API will be available at `http://localhost:8000`.

---

## API Documentation

Once the server is running, visit the interactive Swagger UI:
**`http://localhost:8000/docs`**

### Key Endpoints

* **POST** `/api/v1/auth/login` - Authenticate user.
* **POST** `/api/v1/chat/message/stream` - Send a message and get a streaming response (SSE).
* **POST** `/api/v1/chat/message/edit` - Edit a previous message and regenerate the flow.
* **GET** `/api/v1/chat/history` - Fetch sidebar chat list.
* **GET** `/api/v1/chat/history/{id}` - Fetch full conversation.

---

## How "Smart Memory" Works

To prevent context window overflow while keeping costs low, the backend employs a **Graph-based Node (`history_management`)**:

1. **Check:** Does the chat have > 10 unsummarized messages?
2. **Compress:** If yes, it takes the oldest 5 messages.
3. **Synthesize:** It uses a fast LLM (`Llama-Scout`) to merge them into a "Long-Term Summary" string stored in the `chats` table.
4. **Inject:** Future prompts receive: `(Summary) + (Recent 5 Messages) + (RAG Context)`.

---

## Author

**Hammad Wakeel** * [GitHub Profile](https://www.google.com/url?sa=E&source=gmail&q=https://github.com/hammadwakeel)

* *Expert in AI/ML Backends, RAG Architectures, and Full-Stack Development.*

---

*Built with ❤️ using Python & Supabase.*
