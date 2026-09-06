# AI Film Studio Architecture Diagram

```mermaid
flowchart LR
    subgraph client ["Client Apps"]
        reactApp["React Studio App"]
    end

    subgraph gateway ["API Layer"]
        fastApi["FastAPI App: routers, middleware, WebSockets"]
    end

    subgraph service ["Backend Services"]
        projectWorkflow["Project, Script, Workflow Services"]
        intelligence["Studio Brain, Co-Director, Crew Intelligence"]
        renderService["Render Service"]
        queueWorker["Production Queue Worker and Render Poller"]
        mediaMemory["Video Asset, Keyframe, Semantic Memory"]
        audioAssembly["Audio, Stitching, Export Services"]
    end

    subgraph datastore ["Data Stores"]
        sqlite["SQLite studio.db"]
        outputFiles["Mounted output files: outputs, static, previs-assets"]
        projectStore["Legacy project_store mirror"]
    end

    subgraph external ["External Providers"]
        videoProviders["Video providers: Runway, HappyHorse, Wan, OpenRouter, Higgsfield"]
        llmProviders["LLM and vision providers: Qwen, OpenRouter, Groq, Gemini"]
        audioProviders["Audio providers and local models: ElevenLabs, CosyVoice, Coqui, Stable Audio"]
        ffmpeg["FFmpeg"]
    end

    reactApp <-->|"Fetch API and WebSocket"| fastApi
    fastApi -->|"Project and scene routes"| projectWorkflow
    fastApi -->|"Brain and memory routes"| intelligence
    fastApi -->|"Render routes"| renderService
    fastApi -->|"Queue routes"| queueWorker
    fastApi -->|"Media routes"| mediaMemory
    fastApi -->|"Audio export routes"| audioAssembly

    projectWorkflow -->|"Reads/Writes projects, scenes, workflow"| sqlite
    projectWorkflow -->|"Syncs legacy state"| projectStore
    projectWorkflow -->|"Feeds production context"| intelligence
    projectWorkflow -->|"Enqueues scene work"| queueWorker

    intelligence -->|"Reads/Writes memory, traces, decisions"| sqlite
    intelligence -.->|"Intelligence: advisory calls"| llmProviders

    queueWorker -->|"Claims work and records attempts"| sqlite
    queueWorker -->|"Dispatches renders"| renderService
    queueWorker -->|"Dispatches assembly work"| audioAssembly

    renderService -->|"Persists jobs and provider configs"| sqlite
    renderService -->|"Registers completed assets"| mediaMemory
    renderService -.->|"RenderService: submit and poll jobs"| videoProviders
    renderService -.->|"RenderService: adherence checks"| llmProviders

    mediaMemory -->|"Stores assets, keyframes, memories"| sqlite
    mediaMemory -->|"Reads/Writes media files"| outputFiles
    mediaMemory -.->|"MediaMemory: frame extraction"| ffmpeg
    mediaMemory -.->|"MediaMemory: visual analysis"| llmProviders

    audioAssembly -->|"Persists packages, cuts, audio state"| sqlite
    audioAssembly -->|"Writes MP4, WAV, package artifacts"| outputFiles
    audioAssembly -.->|"AudioAssembly: synthesize tracks"| audioProviders
    audioAssembly -.->|"AudioAssembly: stitch and transcode"| ffmpeg
```

## Notes

- The frontend resolves API calls through `STUDIO_API_BASE`; in local dev, Vite proxies `/api`, `/health`, `/outputs`, and `/previs-assets` to the FastAPI backend on port `8010`.
- The backend is a FastAPI monolith: routes stay thin and route requests into service-layer modules.
- `DatabaseStorage` owns the SQLite-backed project, render, queue, memory, media, workflow, and export tables.
- Long-running work is handled by FastAPI lifespan tasks: production queue worker, render polling, and database backup scheduling.
- External video generation is provider-adapter mediated through `RenderService`; routes should not call provider adapters directly.
