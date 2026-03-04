# StylePal User Flow

User flows and architecture for the StylePal wardrobe intelligence app.

## High-Level User Flow

```mermaid
flowchart LR
    A([Open App]) --> B[Ask<br/>outfit / style / wardrobe]
    B --> C[Get Suggestions]
    C --> D{Pick or Feedback}
    D -->|Pick option / 👍| E[Record & Learn]
    D -->|👎 / Refine| B
    E --> B
```

## Main User Flow

```mermaid
flowchart TB
    subgraph Entry["Entry"]
        Start([Start])
        Home[Home Page]
        Chat[Chat Component]
    end

    subgraph ChatFlow["Chat Flow"]
        Input[User Input<br/>e.g. outfit request]
        SendMsg[Send Message]
        API[POST /stylist/plan]
        Agent[Stylist Agent<br/>LangGraph]
    end

    subgraph AgentTools["Agent Tools"]
        RAG[retrieve_style_knowledge<br/>RAG from Qdrant]
        Wardrobe[get_wardrobe<br/>Fetch user items]
        Weather[get_weather<br/>Open-Meteo]
        UpdateWorn[update_last_worn]
        UpdateProfile[update_profile]
        AddItem[add_wardrobe_item]
        Deprecate[deprecate_wardrobe_item]
    end

    subgraph Intent["Intent Routing"]
        OutfitReq[Outfit Request]
        StyleQA[Style Question]
        ProfileUpd[Profile Update]
        PickThumbs[Pick Option / Thumbs]
    end

    subgraph Responses["Response Types"]
        OutfitResp[OUTFIT 1 & 2<br/>with id references]
        ClarifyResp[Clarifying Questions<br/>location, dates, events]
        InfoResp[Informational Answer]
    end

    subgraph Feedback["User Feedback"]
        Pick1[Pick Option 1]
        Pick2[Pick Option 2]
        ThumbsUp[👍 Thumbs Up]
        ThumbsDown[👎 Thumbs Down]
    end

    subgraph ClarifyFlow["Clarify Flow"]
        ClarifyNode[Clarify Node]
        WhatChange[What would you like to change?<br/>more casual, colors, pieces?]
    end

    subgraph RecordFlow["Record & Learn"]
        RecordOutfit[Record outfit<br/>update_last_worn]
        Episodic[Episodic Memory<br/>positive/negative episodes]
    end

    Start --> Home
    Home --> Chat
    Chat --> Input
    Input --> SendMsg
    SendMsg --> API
    API --> Agent

    Agent --> Intent
    Intent --> OutfitReq
    Intent --> StyleQA
    Intent --> ProfileUpd
    Intent --> PickThumbs

    OutfitReq --> Wardrobe
    OutfitReq --> RAG
    OutfitReq --> Weather
    Wardrobe --> Agent
    RAG --> Agent
    Weather --> Agent

    StyleQA --> RAG
    RAG --> Agent

    ProfileUpd --> UpdateProfile
    UpdateProfile --> Agent

    AddItem --> Agent
    Deprecate --> Agent

    Agent --> Responses
    OutfitResp --> Feedback

    Pick1 --> RecordOutfit
    Pick2 --> RecordOutfit
    ThumbsUp --> RecordOutfit
    ThumbsDown --> ClarifyNode

    ClarifyNode --> WhatChange
    WhatChange --> Input

    RecordOutfit --> Episodic
    Episodic --> Input

    PickThumbs --> UpdateWorn
    UpdateWorn --> Agent
```

## Simplified App Architecture

```mermaid
flowchart LR
    subgraph Frontend["Frontend (Next.js)"]
        Layout[layout.tsx]
        Page[page.tsx]
        Chat[chat.tsx]
        UI[ui/*.tsx]
    end

    subgraph Backend["Backend (FastAPI)"]
        Main[main.py]
        WardrobeR[wardrobe router]
        ProfileR[profile router]
        StylistR[stylist router]
    end

    subgraph Services["Services"]
        Agent[agent.py LangGraph]
        RAG[rag.py Qdrant]
        Memory[memory.py JSON]
        Weather[weather.py]
    end

    Layout --> Page
    Page --> Chat
    Chat --> |POST /stylist/plan| StylistR
    StylistR --> Agent
    Agent --> RAG
    Agent --> Memory
    Agent --> Weather
    Agent --> WardrobeR
    Agent --> ProfileR
```

## Key Interactions

| Interaction | Flow |
|-------------|------|
| **Outfit request** | User asks (e.g. "Outfit for client meeting tomorrow") → Agent calls `get_wardrobe`, `retrieve_style_knowledge`, `get_weather` → Returns OUTFIT 1 and OUTFIT 2 with `[id=X]` references |
| **Pick option** | User clicks "Pick Option 1" or "Pick Option 2" → Agent calls `update_last_worn` → Brief confirmation |
| **Thumbs up** | User clicks 👍 → `update_last_worn` if outfit was suggested, else acknowledgment → Episodic memory records positive outcome |
| **Thumbs down** | User clicks 👎 → Clarify node asks "What would you like to change?" |
| **Profile update** | User says "I prefer tailored fits" / "I'm pear-shaped" → Agent calls `update_profile` |
| **Add item** | User says "I bought a navy blazer" → Agent calls `add_wardrobe_item` |
| **Remove item** | User requests removal → Agent shows matching items with ids → User confirms → Agent calls `deprecate_wardrobe_item` |
| **Clarifying questions** | For vague or multi-day requests, agent asks about location, dates, event types, dress codes before suggesting outfits |

## Related Docs

- [Infrastructure Diagram](./infrastructure-diagram.md) — stack overview and tooling
- [Build Plan](./BUILD_PLAN.md) — roadmap and planned features
