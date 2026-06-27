---
title: LLM Providers
description: All supported LLM providers, model strings, and API key configuration
---

# LLM Providers

Agentspan supports 15+ AI providers. Set the environment variables for the providers you want to use before starting the server. The server auto-enables each provider when its key is present — no manual integration setup needed.

## Quick Setup

```bash
# OpenAI
export OPENAI_API_KEY=sk-...

# Anthropic
export ANTHROPIC_API_KEY=sk-ant-...

# Google Gemini
export GEMINI_API_KEY=AI...
export GOOGLE_CLOUD_PROJECT=your-gcp-project-id

# Then start the server
agentspan server start
```

## Model Format

Specify models in your agents using `provider/model-name`:

```python
agent = Agent(name="bot", model="openai/gpt-4o")
agent = Agent(name="bot", model="anthropic/claude-sonnet-4-6")
agent = Agent(name="bot", model="google_gemini/gemini-2.0-flash")
```

## All Providers

### OpenAI

| Variable | Description |
|---|---|
| `OPENAI_API_KEY` | API key from [platform.openai.com](https://platform.openai.com/api-keys) |
| `OPENAI_ORG_ID` | Organization ID (optional) |

**Models:** `openai/gpt-4o`, `openai/gpt-4o-mini`, `openai/gpt-4-turbo`, `openai/o1`, `openai/o1-mini`, `openai/o3-mini`

**Embeddings:** `openai/text-embedding-3-small`, `openai/text-embedding-3-large`

---

### Anthropic (Claude)

| Variable | Description |
|---|---|
| `ANTHROPIC_API_KEY` | API key from [console.anthropic.com](https://console.anthropic.com/) |

**Models:** `anthropic/claude-opus-4-20250514`, `anthropic/claude-sonnet-4-6`, `anthropic/claude-3-5-sonnet-20241022`, `anthropic/claude-3-haiku-20240307`

---

### Google Gemini

| Variable | Description |
|---|---|
| `GEMINI_API_KEY` | API key from [aistudio.google.com](https://aistudio.google.com/apikey) |
| `GOOGLE_CLOUD_PROJECT` | **Required.** Your GCP project ID |

**Models:** `google_gemini/gemini-2.0-flash`, `google_gemini/gemini-1.5-pro`, `google_gemini/gemini-1.5-flash`

**Embeddings:** `google_gemini/text-embedding-004`

---

### Azure OpenAI

| Variable | Description |
|---|---|
| `AZURE_OPENAI_API_KEY` | API key from Azure portal |
| `AZURE_OPENAI_ENDPOINT` | **Required.** Endpoint URL, e.g. `https://your-resource.openai.azure.com` |
| `AZURE_OPENAI_DEPLOYMENT` | **Required.** Deployment name |

**Models:** `azure_openai/gpt-4o`, `azure_openai/gpt-4`, `azure_openai/gpt-3.5-turbo`

---

### AWS Bedrock

| Variable | Description |
|---|---|
| `AWS_ACCESS_KEY_ID` | AWS access key |
| `AWS_SECRET_ACCESS_KEY` | AWS secret key |

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

### DeepSeek

| Variable | Description |
|---|---|
| `DEEPSEEK_API_KEY` | API key from DeepSeek |

**Models:** `deepseek/deepseek-chat`

---

### Ollama (local)

No API key required. Ollama must be running and reachable.

| Variable | Description |
|---|---|
| `OLLAMA_BASE_URL` | Ollama server URL (default: `http://localhost:11434`) |

**Models:** `ollama/llama3`, `ollama/mistral`, `ollama/phi3`, `ollama/codellama`

**Embeddings:** `ollama/nomic-embed-text`

Install Ollama: [ollama.com/download](https://ollama.com/download)

---

## Summary

| Provider | Env Var | Model Prefix |
|---|---|---|
| OpenAI | `OPENAI_API_KEY` | `openai/` |
| Anthropic | `ANTHROPIC_API_KEY` | `anthropic/` |
| Google Gemini | `GEMINI_API_KEY` + `GOOGLE_CLOUD_PROJECT` | `google_gemini/` |
| Azure OpenAI | `AZURE_OPENAI_API_KEY` + endpoint + deployment | `azure_openai/` |
| AWS Bedrock | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` | `aws_bedrock/` |
| Mistral | `MISTRAL_API_KEY` | `mistral/` |
| Cohere | `COHERE_API_KEY` | `cohere/` |
| Grok / xAI | `XAI_API_KEY` | `grok/` |
| Perplexity | `PERPLEXITY_API_KEY` | `perplexity/` |
| Hugging Face | `HUGGINGFACE_API_KEY` | `hugging_face/` |
| Stability AI | `STABILITY_API_KEY` | `stabilityai/` |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek/` |
| Ollama | `OLLAMA_BASE_URL` | `ollama/` |
