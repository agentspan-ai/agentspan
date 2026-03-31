<p align="center">
  <img src="https://github.com/agentspan/agentspan/raw/main/assets/logo-light.png#gh-light-mode-only" alt="Agentspan" width="400">
  <img src="https://github.com/agentspan/agentspan/raw/main/assets/logo-dark.png#gh-dark-mode-only" alt="Agentspan" width="400">
</p>

<p align="center">
  <a href="https://github.com/agentspan/agentspan/stargazers"><img src="https://img.shields.io/github/stars/agentspan/agentspan?style=social" alt="Stars"></a>
  <a href="https://github.com/agentspan/agentspan/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="License"></a>
  <a href="https://discord.gg/agentspan"><img src="https://img.shields.io/discord/1234567890?label=Discord&logo=discord&color=5865F2" alt="Discord"></a>
</p>

<p align="center">
  <a href="https://github.com/agentspan/agentspan">Main Repo</a> &bull;
  <a href="https://docs.agentspan.dev">Docs</a> &bull;
  <a href="https://discord.gg/agentspan">Discord</a> &bull;
  <a href="../sdk/python/">Python SDK</a> &bull;
  <a href="../cli/">CLI</a>
</p>

---

# Agentspan Server

The durable runtime server that executes AI agents as workflows. Compiles agent definitions into orchestrated workflows, manages LLM interactions, tool execution, streaming, and human-in-the-loop approvals — independently of the client process.

## Quickstart

### Prerequisites

- Java 21+
- Gradle 8+ (included via `gradlew`)

### Build and run

```bash
cd server

# Build
./gradlew bootJar

# Build a size-optimized shaded executable jar
# This is more aggressive about trimming transitive bytecode than bootJar.
./gradlew shadowJar

# Run with default config (SQLite)
java -jar build/libs/agentspan-runtime.jar

# Run the shaded/minimized variant
java -jar build/libs/agentspan-runtime-shaded.jar

# Run with PostgreSQL
java -jar build/libs/agentspan-runtime.jar --spring.profiles.active=postgres
```

Or use the CLI:

```bash
agentspan server start --local
```

For container builds, the Dockerfile now accepts an alternate Gradle task and jar name:

```bash
docker build -f server/Dockerfile \
  --build-arg GRADLE_TASK=shadowJar \
  --build-arg RUNTIME_JAR=agentspan-runtime-shaded.jar \
  -t agentspan/server:shaded .
```

### Set LLM provider API keys

Providers are auto-enabled when their API key is set as an environment variable:

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
# See full list in Configuration section
```

## REST API

**Base path:** `/api/agent`

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Health check |
| `POST` | `/compile` | Compile AgentConfig → WorkflowDef (no execution) |
| `POST` | `/start` | Compile, register, and execute an agent |
| `GET` | `/stream/{executionId}` | SSE event stream (supports `Last-Event-ID` for reconnection) |
| `POST` | `/{executionId}/respond` | HITL response (approve/deny/message) |
| `GET` | `/{executionId}/status` | Polling-based execution status |
| `GET` | `/list` | List all registered agents |
| `GET` | `/get/{name}` | Get agent definition (`?version=X` optional) |
| `DELETE` | `/delete/{name}` | Delete agent definition (`?version=X` optional) |
| `GET` | `/executions` | Search executions (filters: agentName, status, freeText, sort) |
| `GET` | `/executions/{executionId}` | Detailed execution status |

### SSE Event Types

| Event | Description |
|-------|-------------|
| `thinking` | LLM is generating a response |
| `tool_call` | Tool invocation started |
| `tool_result` | Tool returned a result |
| `handoff` | Agent delegated to a sub-agent |
| `waiting` | Paused for human approval |
| `guardrail_pass` | Guardrail check passed |
| `guardrail_fail` | Guardrail check failed |
| `error` | Error occurred |
| `done` | Agent execution completed |

Reconnection is supported via `Last-Event-ID` header. Events are buffered in memory (up to 200 per workflow).

## Database

### SQLite (default)

Zero setup. Data is stored in `agent-runtime.db` in the working directory using WAL mode for concurrent reads.

```properties
conductor.db.type=sqlite
spring.datasource.url=jdbc:sqlite:agent-runtime.db?busy_timeout=15000&journal_mode=WAL
```

### PostgreSQL (production)

For production workloads with concurrent access and durability guarantees.

**1. Start PostgreSQL:**

```bash
docker compose up -d
```

This starts PostgreSQL 16 with user `conductor`, password `conductor`, database `conductor`.

**2. Run with the Postgres profile:**

```bash
java -jar build/libs/agentspan-runtime.jar --spring.profiles.active=postgres
```

Or via environment variables:

```bash
export SPRING_PROFILES_ACTIVE=postgres
export SPRING_DATASOURCE_URL=jdbc:postgresql://your-host:5432/conductor
export SPRING_DATASOURCE_USERNAME=your_user
export SPRING_DATASOURCE_PASSWORD=your_password
java -jar build/libs/agentspan-runtime.jar
```

## RAG (Vector Search)

The server supports RAG (Retrieval-Augmented Generation) via built-in `LLM_INDEX_TEXT` and `LLM_SEARCH_INDEX` system tasks. These let agents index documents into a vector database and search them — no external RAG service needed.

Activate with the `rag` Spring profile:

```bash
java -jar build/libs/agentspan-runtime.jar --spring.profiles.active=rag

# Combine with PostgreSQL backend:
java -jar build/libs/agentspan-runtime.jar --spring.profiles.active=postgres,rag
```

### Supported Vector Databases

#### PostgreSQL + pgvector

Uses [pgvector](https://github.com/pgvector/pgvector) for vector similarity search in PostgreSQL.

**1. Install pgvector:**

```bash
# macOS (Homebrew)
brew install pgvector

# Ubuntu/Debian
sudo apt install postgresql-16-pgvector

# Docker (pgvector is included in the official image)
docker run -d --name pgvector -e POSTGRES_PASSWORD=postgres -p 5432:5432 pgvector/pgvector:pg16
```

**2. Create the database and enable the extension:**

```sql
CREATE DATABASE agentspan;
\c agentspan
CREATE EXTENSION IF NOT EXISTS vector;
```

**3. Configure** in `application-rag.properties` (already included):

```properties
conductor.vectordb.instances[0].name=pgvectordb
conductor.vectordb.instances[0].type=postgres
conductor.vectordb.instances[0].postgres.datasourceURL=jdbc:postgresql://localhost:5432/agentspan
conductor.vectordb.instances[0].postgres.user=postgres
conductor.vectordb.instances[0].postgres.password=postgres
conductor.vectordb.instances[0].postgres.dimensions=1536
conductor.vectordb.instances[0].postgres.distanceMetric=cosine
conductor.vectordb.instances[0].postgres.indexingMethod=ivfflat
```

Override via environment variables: `PGVECTOR_JDBC_URL`, `PGVECTOR_USER`, `PGVECTOR_PASSWORD`, `PGVECTOR_DIMENSIONS`, `PGVECTOR_DISTANCE`, `PGVECTOR_INDEX_METHOD`.

Tables and indexes are created automatically on first use.

#### Pinecone

**1.** Create an index at [app.pinecone.io](https://app.pinecone.io) with the desired dimensions (e.g. 1536 for `text-embedding-3-small`).

**2.** Add to `application-rag.properties`:

```properties
conductor.vectordb.instances[0].name=pineconedb
conductor.vectordb.instances[0].type=pinecone
conductor.vectordb.instances[0].pinecone.apiKey=${PINECONE_API_KEY}
conductor.vectordb.instances[0].pinecone.projectName=your-project
conductor.vectordb.instances[0].pinecone.environment=us-east-1
```

#### MongoDB Atlas Vector Search

**1.** Create a MongoDB Atlas cluster and enable [Atlas Vector Search](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/) on your collection.

**2.** Add to `application-rag.properties`:

```properties
conductor.vectordb.instances[0].name=mongodb_atlas
conductor.vectordb.instances[0].type=mongodb_atlas
conductor.vectordb.instances[0].mongodb.connectionString=${MONGODB_URI:mongodb+srv://user:pass@cluster.mongodb.net}
conductor.vectordb.instances[0].mongodb.databaseName=vectordb
conductor.vectordb.instances[0].mongodb.collectionName=embeddings
```

### SDK Usage

```python
from agentspan.agents import Agent, search_tool, index_tool

kb_search = search_tool(
    name="search_docs",
    description="Search the knowledge base.",
    vector_db="pgvectordb",          # matches instances[0].name
    index="product_docs",
    embedding_model_provider="openai",
    embedding_model="text-embedding-3-small",
)

kb_index = index_tool(
    name="index_doc",
    description="Add a document to the knowledge base.",
    vector_db="pgvectordb",
    index="product_docs",
    embedding_model_provider="openai",
    embedding_model="text-embedding-3-small",
)

agent = Agent(
    name="rag_assistant",
    model="openai/gpt-4o",
    tools=[kb_search, kb_index],
    instructions="Search the knowledge base before answering questions.",
)
```

See [`examples/adk/35_rag_agent.py`](../sdk/python/examples/adk/35_rag_agent.py) for a full end-to-end example.

## Configuration

### Server Settings

| Property | Env Var | Default |
|----------|---------|---------|
| `server.port` | `SERVER_PORT` | `6767` |
| `conductor.db.type` | — | `sqlite` |
| `spring.datasource.url` | `SPRING_DATASOURCE_URL` | `jdbc:sqlite:agent-runtime.db` |
| `spring.datasource.username` | `SPRING_DATASOURCE_USERNAME` | — |
| `spring.datasource.password` | `SPRING_DATASOURCE_PASSWORD` | — |
| `spring.datasource.hikari.maximum-pool-size` | `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE` | `8` |

### AI Providers

Providers are auto-enabled when their API key env var is set. No manual integration setup needed.

| Provider | Env Var(s) | Models |
|----------|-----------|--------|
| OpenAI | `OPENAI_API_KEY` | GPT-4o, o1, o3-mini, DALL-E 3, text-embedding-3 |
| Anthropic | `ANTHROPIC_API_KEY` | Claude Opus 4, Sonnet 4, 3.5 Sonnet, Haiku |
| Google Gemini | `GEMINI_API_KEY`, `GOOGLE_CLOUD_PROJECT` | Gemini 2.0 Flash, 1.5 Pro |
| Azure OpenAI | `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` | GPT-4o via Azure |
| AWS Bedrock | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION` | Claude, Llama, Titan via AWS |
| Mistral | `MISTRAL_API_KEY` | Mistral Large, Small, Mixtral |
| Cohere | `COHERE_API_KEY` | Command-R+, Command-R |
| Grok / xAI | `XAI_API_KEY` | Grok-3, Grok-3-mini |
| Perplexity | `PERPLEXITY_API_KEY` | Sonar Pro, Sonar |
| HuggingFace | `HUGGINGFACE_API_KEY` | Llama 3, Mistral, Zephyr |
| Stability AI | `STABILITY_API_KEY` | SD3.5-large, Stable Image Core |
| Ollama (local) | `OLLAMA_HOST` | llama3, mistral, phi3, codellama |

### Metrics

The server supports metrics export via Micrometer. All exporters are disabled by default and can be enabled via properties:

- Prometheus, Datadog, CloudWatch, Azure Monitor, New Relic, InfluxDB, Elastic, StatsD, Dynatrace, Stackdriver, Atlas, OTLP, JMX

## Architecture

The server is a Spring Boot application (Java 21) built on top of [Conductor](https://github.com/conductor-oss/conductor), a battle-tested workflow orchestration engine.

```
   SDK                        CLI
    │                          │
    └──── Agent config JSON ───┘
                │
         POST /api/agent/start
                │
         ┌──────▼──────┐
         │   Compiler  │  AgentConfig → WorkflowDef
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │  Conductor  │  Workflow engine (execution, retry, persistence)
         └──────┬──────┘
                │
         ┌──────▼──────┐
         │  AI Workers │  LLM calls, tool dispatch, guardrails
         └──────┬──────┘
                │
         SSE event stream → client
```

**Key components:**

| Package | Purpose |
|---------|---------|
| `dev.agentspan.runtime.compiler` | Compiles `AgentConfig` → Conductor `WorkflowDef` |
| `dev.agentspan.runtime.controller` | REST API endpoints |
| `dev.agentspan.runtime.service` | Business logic, SSE streaming, event handling |
| `dev.agentspan.runtime.model` | DTOs: AgentConfig, StartRequest, AgentSSEEvent |
| `dev.agentspan.runtime.normalizer` | Configuration normalization |
| `dev.agentspan.runtime.util` | Model parser, JS builder, provider validation |

## Development

### Build

```bash
./gradlew bootJar

# Or build the size-optimized shaded executable
./gradlew shadowJar
```

### Run tests

```bash
./gradlew test
```

Tests use an in-memory SQLite database with AI providers disabled.

### Project structure

```
server/
├── build.gradle                           # Build config (Spring Boot 3.3.5, Java 21)
├── docker-compose.yml                     # PostgreSQL for local dev
├── src/main/
│   ├── java/
│   │   ├── org/conductoross/conductor/
│   │   │   └── AgentRuntime.java          # Spring Boot entry point
│   │   └── dev/agentspan/runtime/
│   │       ├── compiler/                  # AgentConfig → WorkflowDef
│   │       ├── controller/                # REST API
│   │       ├── service/                   # Business logic + SSE
│   │       ├── model/                     # DTOs
│   │       ├── normalizer/                # Config normalization
│   │       └── util/                      # Helpers
│   └── resources/
│       ├── application.properties         # Default config (SQLite)
│       ├── application-postgres.properties
│       └── application-rag.properties     # Vector DB config (pgvector/Pinecone/MongoDB)
└── src/test/
    └── resources/
        └── application-test.properties    # Test config
```

## Community

- **[Discord](https://discord.gg/agentspan)** — Ask questions, share what you're building, get help
- **[GitHub Issues](https://github.com/agentspan/agentspan/issues)** — Bug reports and feature requests
- **[Contributing Guide](../CONTRIBUTING.md)** — How to contribute

If Agentspan is useful to you, help others find it:

- [Star the repo](https://github.com/agentspan/agentspan) — it helps more than you think
- [Share on LinkedIn](https://www.linkedin.com/sharing/share-offsite/?url=https://github.com/agentspan/agentspan) — tell your network
- [Share on X/Twitter](https://twitter.com/intent/tweet?text=Agentspan%20%E2%80%94%20AI%20agents%20that%20don%27t%20die%20when%20your%20process%20does.%20Durable%2C%20scalable%2C%20observable.&url=https://github.com/agentspan/agentspan) — spread the word

## License

[MIT](../LICENSE)
