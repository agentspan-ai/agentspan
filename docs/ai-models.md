# AI Model Configuration

Agentspan supports 12+ AI providers out of the box. Configure them by setting environment variables before starting the server.

## Quick Setup

Set the API key for the provider(s) you want to use:

```bash
# OpenAI (most common)
export OPENAI_API_KEY=sk-...

# Anthropic (Claude)
export ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini
export GEMINI_API_KEY=AI...
export GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# Then start the server
agentspan server start
```

## All Providers

### OpenAI

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | API key from [platform.openai.com](https://platform.openai.com/api-keys) |
| `OPENAI_ORG_ID` | Organization ID (optional) |

**Models:** `openai/gpt-4o`, `openai/gpt-4o-mini`, `openai/gpt-4-turbo`, `openai/o1`, `openai/o1-mini`, `openai/o3-mini`

**Embeddings:** `openai/text-embedding-3-small`, `openai/text-embedding-3-large`

**Image generation:** `openai/dall-e-3`

---

### Anthropic (Claude)

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | API key from [console.anthropic.com](https://console.anthropic.com/) |

**Models:** `anthropic/claude-opus-4-20250514`, `anthropic/claude-sonnet-4-20250514`, `anthropic/claude-3-5-sonnet-20241022`, `anthropic/claude-3-haiku-20240307`

---

### Google Gemini

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | API key from [aistudio.google.com](https://aistudio.google.com/apikey) |
| `GOOGLE_CLOUD_PROJECT` | **Required.** GCP project ID |

**Models:** `google_gemini/gemini-2.0-flash`, `google_gemini/gemini-1.5-pro`, `google_gemini/gemini-1.5-flash`

**Embeddings:** `google_gemini/text-embedding-004`

**Image generation:** `google_gemini/imagen-3.0-generate-002`

---

### Azure OpenAI

| Variable | Description |
|---|---|
| `AZURE_OPENAI_API_KEY` | API key from Azure portal |
| `AZURE_OPENAI_ENDPOINT` | **Required.** Endpoint URL (e.g. `https://your-resource.openai.azure.com`) |
| `AZURE_OPENAI_DEPLOYMENT` | **Required.** Deployment name |

**Models:** `azure_openai/gpt-4o`, `azure_openai/gpt-4`, `azure_openai/gpt-3.5-turbo`

---

### AWS Bedrock

| Variable | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |

**Server properties (optional):**
- `conductor.ai.bedrock.region` — defaults to `us-east-1`

**Models:** `aws_bedrock/anthropic.claude-3-5-sonnet-20241022-v2:0`, `aws_bedrock/anthropic.claude-3-haiku-20240307-v1:0`, `aws_bedrock/meta.llama3-70b-instruct-v1:0`, `aws_bedrock/amazon.titan-text-express-v1`

**Embeddings:** `aws_bedrock/amazon.titan-embed-text-v2:0`

---

### Mistral AI

| Variable | Description |
|---|---|
| `MISTRAL_API_KEY` | API key from [console.mistral.ai](https://console.mistral.ai/) |

**Models:** `mistral/mistral-large-latest`, `mistral/mistral-medium-latest`, `mistral/mistral-small-latest`, `mistral/open-mixtral-8x7b`

**Embeddings:** `mistral/mistral-embed`

---

### Cohere

| Variable | Description |
|---|---|
| `COHERE_API_KEY` | API key from [dashboard.cohere.com](https://dashboard.cohere.com/) |

**Models:** `cohere/command-r-plus`, `cohere/command-r`, `cohere/command`

**Embeddings:** `cohere/embed-english-v3.0`, `cohere/embed-multilingual-v3.0`

---

### Grok (xAI)

| Variable | Description |
|---|---|
| `XAI_API_KEY` | API key from xAI |

**Models:** `grok/grok-3`, `grok/grok-3-mini`

---

### Perplexity AI

| Variable | Description |
|---|---|
| `PERPLEXITY_API_KEY` | API key from [perplexity.ai](https://www.perplexity.ai/) |

**Models:** `perplexity/sonar-pro`, `perplexity/sonar`

---

### Hugging Face

| Variable | Description |
|---|---|
| `HUGGINGFACE_API_KEY` | API token from [huggingface.co](https://huggingface.co/settings/tokens) |

**Models:** `hugging_face/meta-llama/Llama-3-70b-chat-hf`, `hugging_face/mistralai/Mistral-7B-Instruct-v0.2`

---

### Stability AI

| Variable | Description |
|---|---|
| `STABILITY_API_KEY` | API key from [platform.stability.ai](https://platform.stability.ai/) |

**Image generation:** `stabilityai/sd3.5-large`, `stabilityai/sd3.5-medium`, `stabilityai/stable-image-core`

---

### Ollama (Local / Remote)

No API key required. Ollama must be running and reachable.

| Variable | Description |
|---|---|
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |

```bash
# Local (default)
# No configuration needed if Ollama is running on localhost

# Remote or custom port
export OLLAMA_BASE_URL=http://your-gpu-server:11434
```

Install Ollama: [ollama.com/download](https://ollama.com/download)

**Models:** `ollama/llama3`, `ollama/mistral`, `ollama/phi3`, `ollama/codellama`

**Embeddings:** `ollama/nomic-embed-text`

---

## Model Format

When specifying models in your agents, use the format `provider/model-name`:

```python
agent = Agent(name="my_agent", model="openai/gpt-4o")
agent = Agent(name="my_agent", model="anthropic/claude-sonnet-4-20250514")
agent = Agent(name="my_agent", model="google_gemini/gemini-2.0-flash")
```

## Server Properties

These can be set as environment variables using the Spring Boot convention (dots become underscores, uppercase):

| Property | Env Variable | Default | Description |
|---|---|---|---|
| `conductor.integrations.ai.enabled` | `CONDUCTOR_INTEGRATIONS_AI_ENABLED` | `true` | Enable/disable AI integration |
| `conductor.ai.openai.api-key` | `OPENAI_API_KEY` | — | OpenAI API key |
| `conductor.ai.openai.organization-id` | `OPENAI_ORG_ID` | — | OpenAI organization |
| `conductor.ai.anthropic.api-key` | `ANTHROPIC_API_KEY` | — | Anthropic API key |
| `conductor.ai.gemini.api-key` | `GEMINI_API_KEY` | — | Google Gemini API key |
| `conductor.ai.gemini.project-id` | `GOOGLE_CLOUD_PROJECT` | — | GCP project ID |
| `conductor.ai.gemini.location` | — | `us-central1` | GCP region |
| `conductor.ai.azureopenai.api-key` | `AZURE_OPENAI_API_KEY` | — | Azure OpenAI API key |
| `conductor.ai.azureopenai.base-url` | `AZURE_OPENAI_ENDPOINT` | — | Azure OpenAI endpoint |
| `conductor.ai.azureopenai.deployment-name` | `AZURE_OPENAI_DEPLOYMENT` | — | Azure deployment name |
| `conductor.ai.bedrock.access-key` | `AWS_ACCESS_KEY_ID` | — | AWS access key |
| `conductor.ai.bedrock.secret-key` | `AWS_SECRET_ACCESS_KEY` | — | AWS secret key |
| `conductor.ai.bedrock.region` | — | `us-east-1` | AWS region |
| `conductor.ai.mistral.api-key` | `MISTRAL_API_KEY` | — | Mistral API key |
| `conductor.ai.cohere.api-key` | `COHERE_API_KEY` | — | Cohere API key |
| `conductor.ai.grok.api-key` | `XAI_API_KEY` | — | Grok/xAI API key |
| `conductor.ai.perplexity.api-key` | `PERPLEXITY_API_KEY` | — | Perplexity API key |
| `conductor.ai.huggingface.api-key` | `HUGGINGFACE_API_KEY` | — | Hugging Face token |
| `conductor.ai.stabilityai.api-key` | `STABILITY_API_KEY` | — | Stability AI API key |
| `conductor.ai.ollama.base-url` | `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
