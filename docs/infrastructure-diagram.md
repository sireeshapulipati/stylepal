# Stylepal Infrastructure Diagram

## Stack Overview

```mermaid
flowchart TB
    subgraph Client["Client Layer"]
        Browser["Browser"]
    end

    subgraph Frontend["Frontend (Next.js 16)"]
        NextApp["Next.js App Router"]
        ChatUI["Chat Component"]
        WardrobeUI["Wardrobe UI"]
        ProfileUI["Profile UI"]
        NextApp --> ChatUI
        NextApp --> WardrobeUI
        NextApp --> ProfileUI
    end

    subgraph Backend["Backend (FastAPI)"]
        API["FastAPI API"]
        StylistRouter["/stylist/plan"]
        WardrobeRouter["/wardrobe"]
        ProfileRouter["/profile"]
        API --> StylistRouter
        API --> WardrobeRouter
        API --> ProfileRouter
    end

    subgraph Agent["Stylist Agent (LangGraph)"]
        Graph["LangGraph StateGraph"]
        Tools["Tool Node"]
        LLM["Gemini 2.5 Flash"]
        Graph --> Graph
        Graph --> Tools
        Graph --> LLM
    end

    subgraph ToolsDetail["Agent Tools"]
        GetWardrobe["get_wardrobe"]
        RAG["retrieve_style_knowledge"]
        GetWeather["get_weather"]
        UpdateProfile["update_profile"]
        AddItem["add_wardrobe_item"]
        DeprecateItem["deprecate_wardrobe_item"]
        UpdateLastWorn["update_last_worn"]
    end

    subgraph Data["Data Layer"]
        SQLite[(SQLite\nstylepal.db)]
        Qdrant[(Qdrant Cloud\nstyle_knowledge)]
        JSON["JSON Files\n(profile, outfit_history, episodes)"]
    end

    subgraph External["External APIs"]
        OpenMeteo["Open-Meteo\n(weather + geocoding)"]
    end

    subgraph Eval["Evaluation"]
        Ragas["Ragas"]
        LangSmith["LangSmith (optional)"]
    end

    Browser --> NextApp
    NextApp --> API
    StylistRouter --> Graph
    Tools --> GetWardrobe
    Tools --> RAG
    Tools --> GetWeather
    Tools --> UpdateProfile
    Tools --> AddItem
    Tools --> DeprecateItem
    Tools --> UpdateLastWorn

    GetWardrobe --> SQLite
    AddItem --> SQLite
    DeprecateItem --> SQLite
    UpdateLastWorn --> SQLite
    RAG --> Qdrant
    RAG --> LLM
    GetWeather --> OpenMeteo
    UpdateProfile --> JSON

    LLM --> Qdrant
    Graph --> LangSmith
    Graph --> Ragas
```

## Simplified Architecture

```mermaid
flowchart LR
    subgraph User["User"]
        Browser["Browser"]
    end

    subgraph App["Stylepal"]
        FE["Next.js"]
        API["FastAPI"]
        Agent["LangGraph Agent"]
        FE --> API
        API --> Agent
    end

    subgraph Storage["Storage"]
        DB[(SQLite)]
        VDB[(Qdrant)]
        FS["JSON Files"]
    end

    subgraph AI["AI"]
        Gemini["Gemini"]
    end

    subgraph External["External"]
        Weather["Open-Meteo"]
    end

    Browser --> FE
    Agent --> Gemini
    Agent --> DB
    Agent --> VDB
    Agent --> FS
    Agent --> Weather
```

## Tooling Choices & Rationale

| Component | Choice | Why |
|-----------|--------|-----|
| **Next.js 16** | React framework with App Router | Server components, fast routing, and strong ecosystem for production apps. |
| **shadcn/ui + Radix** | Component library | Accessible, customizable primitives without heavy styling overhead. |
| **Tailwind CSS** | Utility-first CSS | Fast iteration and consistent design tokens without custom CSS. |
| **FastAPI** | Python API framework | Async support, automatic OpenAPI docs, and strong typing for the agent backend. |
| **Uvicorn** | ASGI server | Fast async Python server that fits FastAPI deployments. |
| **SQLite + SQLAlchemy** | Primary database | Zero-config, file-based storage for wardrobe and wear history; easy local dev. |
| **Qdrant Cloud** | Vector database | Managed vector storage for semantic search over style knowledge; 768-dim Gemini embeddings. |
| **Gemini 2.5 Flash** | LLM + embeddings | Single model for chat and embeddings; fast and cost-effective for agent + RAG. |
| **LangGraph** | Agent orchestration | Stateful graph with tool loops; supports multi-turn and memory. |
| **LangChain** | LangChain core | Integrations for tools, prompts, and message handling for the agent. |
| **Open-Meteo** | Weather API | Free, no API key; supports geocoding and date resolution for outfit planning. |
| **JSON files** | Profile & memory | Simple file-based storage for profile, outfit history, and episodes without extra DB. |
| **Ragas** | Evaluation | LLM-based metrics for RAG and agent; supports faithfulness, recall, tool call accuracy. |
| **LangSmith** | Tracing | Optional observability for debugging agent runs and tool calls. |
