# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Tool definitions — @tool decorator and server-side tool constructors.

Tools are **server-first**: ``@tool`` functions become Conductor task definitions
executed by workers.  ``http_tool`` and ``mcp_tool`` create pure server-side
tools that require no worker process at all.
"""

from __future__ import annotations

import functools
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TypeVar, overload

F = TypeVar("F", bound=Callable[..., Any])


# ── ToolContext (dependency injection for tools) ────────────────────────


@dataclass
class ToolContext:
    """Execution context injected into tools that declare a ``context`` parameter.

    Tools that include ``context: ToolContext`` in their signature will
    automatically receive this context at execution time. Tools without it
    work unchanged.

    Attributes:
        session_id: The session ID for the current execution.
        execution_id: The Conductor execution ID.
        agent_name: The name of the agent executing this tool.
        metadata: Arbitrary metadata from the agent.
        dependencies: User-provided dependencies (DB connections, API clients, etc.)
    """

    session_id: str = ""
    execution_id: str = ""
    agent_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    dependencies: Dict[str, Any] = field(default_factory=dict)
    state: Dict[str, Any] = field(default_factory=dict)


# ── ToolDef (serialisable tool definition) ──────────────────────────────


@dataclass
class ToolDef:
    """A fully-resolved tool definition ready for compilation.

    Most users will never create a ``ToolDef`` directly — use the ``@tool``
    decorator, ``http_tool()``, or ``mcp_tool()`` instead.

    Attributes:
        name: Tool name (becomes the Conductor task definition name).
        description: Human-readable description sent to the LLM.
        input_schema: JSON Schema for the tool's input parameters.
        output_schema: JSON Schema for the tool's output.
        func: The Python callable (``None`` for server-side-only tools).
        approval_required: If ``True``, a ``WaitTask`` is inserted before execution.
        timeout_seconds: Max seconds the tool may run before timing out.
        tool_type: ``"worker"`` (Python function), ``"http"``, or ``"mcp"``.
        config: Extra configuration (URL, method, headers, etc.).
    """

    name: str
    description: str = ""
    input_schema: Dict[str, Any] = field(default_factory=dict)
    output_schema: Dict[str, Any] = field(default_factory=dict)
    func: Optional[Callable[..., Any]] = field(default=None, repr=False)
    approval_required: bool = False
    timeout_seconds: Optional[int] = None
    tool_type: str = "worker"
    config: Dict[str, Any] = field(default_factory=dict)
    guardrails: List[Any] = field(default_factory=list)
    isolated: bool = True
    credentials: List[Any] = field(default_factory=list)
    stateful: bool = False


# ── @tool decorator ─────────────────────────────────────────────────────


@overload
def tool(func: F) -> F: ...


@overload
def tool(
    *,
    name: Optional[str] = None,
    external: bool = False,
    approval_required: bool = False,
    timeout_seconds: Optional[int] = None,
    guardrails: Optional[List[Any]] = None,
    isolated: bool = True,
    credentials: Optional[List[Any]] = None,
    stateful: bool = False,
) -> Callable[[F], F]: ...


def tool(
    func: Optional[F] = None,
    *,
    name: Optional[str] = None,
    external: bool = False,
    approval_required: bool = False,
    timeout_seconds: Optional[int] = None,
    guardrails: Optional[List[Any]] = None,
    isolated: bool = True,
    credentials: Optional[List[Any]] = None,
    stateful: bool = False,
) -> Any:
    """Register a Python function as a Conductor agent tool.

    Can be used bare (``@tool``) or with arguments
    (``@tool(approval_required=True)``).

    The decorated function retains its original signature and can still be
    called directly.  A ``_tool_def`` attribute is attached containing the
    resolved :class:`ToolDef`.

    Server-first execution model:
        1. ``@tool`` generates a JSON Schema from type hints + docstring.
        2. The schema is registered as a Conductor task definition.
        3. The function is registered as a Conductor worker.
        4. When the LLM calls this tool, Conductor schedules it as a task.
        5. A worker picks it up, executes the function, and returns the result.

    External workers:
        Use ``@tool(external=True)`` when the worker already exists in another
        process or repository.  The function stub provides the schema (via type
        hints) and description (via docstring), but **no local worker is
        started** — Conductor dispatches the task to whatever worker is polling
        for that task definition name.
    """

    def _wrap(fn: F) -> F:
        tool_name = name or fn.__name__
        description = inspect.getdoc(fn) or ""

        from agentspan.agents._internal.schema_utils import schema_from_function

        schemas = schema_from_function(fn)

        tool_def = ToolDef(
            name=tool_name,
            description=description,
            input_schema=schemas.get("input", {}),
            output_schema=schemas.get("output", {}),
            func=None if external else fn,
            approval_required=approval_required,
            timeout_seconds=timeout_seconds,
            tool_type="worker",
            guardrails=list(guardrails) if guardrails else [],
            isolated=isolated,
            credentials=list(credentials) if credentials else [],
            stateful=stateful,
        )

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        wrapper._tool_def = tool_def  # type: ignore[attr-defined]
        fn._tool_def = tool_def  # type: ignore[attr-defined]  # Also on raw fn for pickling
        return wrapper  # type: ignore[return-value]

    if func is not None:
        return _wrap(func)
    return _wrap


# ── Server-side tool constructors ───────────────────────────────────────


def http_tool(
    name: str,
    description: str,
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    input_schema: Optional[Dict[str, Any]] = None,
    accept: List[str] = ["application/json"],
    content_type: str = "application/json",
    credentials: Optional[List[str]] = None,
) -> ToolDef:
    """Create a tool backed by an HTTP endpoint (Conductor ``HttpTask``).

    No worker process is needed — the Conductor server makes the HTTP call
    directly.

    Headers can reference credentials using ``${NAME}`` syntax. The server
    resolves these at execution time from the credential store.

    Args:
        name: Tool name.
        description: Human-readable description for the LLM.
        url: The HTTP endpoint URL.
        method: HTTP method (GET, POST, PUT, DELETE).
        headers: Optional HTTP headers. Use ``${NAME}`` for credential placeholders.
        input_schema: JSON Schema for the tool's input parameters.
        accept: Value for the ``Accept`` header (default ``application/json``).
        content_type: Value for the ``Content-Type`` header (default ``application/json``).
        credentials: Credential names referenced by ``${NAME}`` in headers.
    """
    import re as _re

    cred_list = list(credentials) if credentials else []

    # Validate: any ${NAME} in headers must be in credentials list
    if headers:
        placeholders = set(_re.findall(r"\$\{(\w+)}", str(headers)))
        if placeholders:
            missing = placeholders - set(cred_list)
            if missing:
                raise ValueError(
                    f"Header placeholder(s) {missing} not declared in credentials={cred_list}. "
                    f"Add them to the credentials list."
                )

    return ToolDef(
        name=name,
        description=description,
        input_schema=input_schema or {"type": "object", "properties": {}},
        tool_type="http",
        config={
            "url": url,
            "method": method.upper(),
            "headers": headers or {},
            "accept": accept,
            "contentType": content_type,
        },
        credentials=cred_list,
    )


def api_tool(
    url: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    tool_names: Optional[List[str]] = None,
    max_tools: int = 64,
    credentials: Optional[List[str]] = None,
) -> ToolDef:
    """Create tool(s) from an OpenAPI spec, Swagger spec, Postman collection, or base URL.

    At compile time the server discovers API operations from the spec and
    expands them into individual tools.  Tool calls execute as standard
    Conductor ``HTTP`` tasks — **no worker process is needed**.

    The server auto-detects the format:

    - **OpenAPI 3.x** — JSON/YAML with ``openapi: "3.*"``
    - **Swagger 2.0** — JSON with ``swagger: "2.0"``
    - **Postman Collection** — JSON with ``info._postman_id`` or ``item[]``
    - **Base URL** — tries ``/openapi.json``, ``/swagger.json``, etc.

    Headers can reference credentials using ``${NAME}`` syntax. The server
    resolves these at execution time from the credential store.

    Args:
        url: URL to the spec, collection, or base URL for auto-discovery.
        name: Optional override name (defaults to spec ``info.title``).
        description: Optional override description.
        headers: Global HTTP headers applied to all discovered endpoints.
            Use ``${NAME}`` for credential placeholders.
        tool_names: Optional whitelist — only include these operation IDs.
        max_tools: If operations exceed this, a filter LLM selects the
            most relevant ones based on the user's prompt (default 64).
        credentials: Credential names referenced by ``${NAME}`` in headers.

    Example::

        stripe = api_tool(
            url="https://api.stripe.com/openapi.json",
            headers={"Authorization": "Bearer ${STRIPE_KEY}"},
            credentials=["STRIPE_KEY"],
            max_tools=20,
        )
    """
    import re as _re

    cred_list = list(credentials) if credentials else []

    # Validate: any ${NAME} in headers must be in credentials list
    if headers:
        placeholders = set(_re.findall(r"\$\{(\w+)}", str(headers)))
        if placeholders:
            missing = placeholders - set(cred_list)
            if missing:
                raise ValueError(
                    f"Header placeholder(s) {missing} not declared in credentials={cred_list}. "
                    f"Add them to the credentials list."
                )

    config: Dict[str, Any] = {"url": url}
    if headers:
        config["headers"] = headers
    if tool_names is not None:
        config["tool_names"] = list(tool_names)
    config["max_tools"] = max_tools
    return ToolDef(
        name=name or "api_tools",
        description=description or f"API tools from {url}",
        tool_type="api",
        config=config,
        credentials=cred_list,
    )


def mcp_tool(
    server_url: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    tool_names: Optional[List[str]] = None,
    max_tools: int = 64,
    credentials: Optional[List[str]] = None,
) -> ToolDef:
    """Create tool(s) from an MCP server (Conductor ``ListMcpTools`` + ``CallMcpTool``).

    At compile time the SDK discovers individual tools from the MCP server
    via Conductor's ``LIST_MCP_TOOLS`` system task and expands them into
    separate ``ToolDef`` instances with proper names, descriptions, and
    input schemas.  Tool calls use the ``CALL_MCP_TOOL`` system task.
    **No worker process is needed** — the Conductor server handles MCP
    protocol communication directly.

    Headers can reference credentials using ``${NAME}`` syntax. The server
    resolves these at execution time from the credential store.

    Args:
        server_url: URL of the MCP server (e.g. ``"http://localhost:3001/mcp"``).
        name: Optional override name (defaults to ``"mcp_tools"``).
        description: Optional override description.
        headers: Optional HTTP headers. Use ``${NAME}`` for credential placeholders.
        tool_names: Optional whitelist — only include these tool names.
        max_tools: Threshold for runtime LLM filtering (default 64).
        credentials: Credential names referenced by ``${NAME}`` in headers.
    """
    import re as _re

    cred_list = list(credentials) if credentials else []

    # Validate: any ${NAME} in headers must be in credentials list
    if headers:
        placeholders = set(_re.findall(r"\$\{(\w+)}", str(headers)))
        if placeholders:
            missing = placeholders - set(cred_list)
            if missing:
                raise ValueError(
                    f"Header placeholder(s) {missing} not declared in credentials={cred_list}. "
                    f"Add them to the credentials list."
                )

    config: Dict[str, Any] = {"server_url": server_url}
    if headers:
        config["headers"] = headers
    if tool_names is not None:
        config["tool_names"] = list(tool_names)
    config["max_tools"] = max_tools
    return ToolDef(
        name=name or "mcp_tools",
        description=description or f"MCP tools from {server_url}",
        tool_type="mcp",
        config=config,
        credentials=cred_list,
    )


# ── Media generation tool constructors ────────────────────────────────

# Tool types that map to Conductor system tasks
MEDIA_TOOL_TYPES = frozenset({"generate_image", "generate_audio", "generate_video", "generate_pdf"})


def _media_tool(
    tool_type: str,
    task_type: str,
    name: str,
    description: str,
    llm_provider: str,
    model: str,
    input_schema: Optional[Dict[str, Any]] = None,
    **defaults: Any,
) -> ToolDef:
    """Internal helper for creating media generation tools."""
    config: Dict[str, Any] = {
        "taskType": task_type,
        "llmProvider": llm_provider,
        "model": model,
    }
    config.update(defaults)
    return ToolDef(
        name=name,
        description=description,
        input_schema=input_schema or {},
        tool_type=tool_type,
        config=config,
    )


def image_tool(
    name: str,
    description: str,
    llm_provider: str,
    model: str,
    input_schema: Optional[Dict[str, Any]] = None,
    **defaults: Any,
) -> ToolDef:
    """Create a tool that generates images (Conductor ``GENERATE_IMAGE`` task).

    No worker process is needed — the Conductor server calls the AI provider
    directly.

    The LLM decides *when* to call this tool and provides dynamic parameters
    (e.g. ``prompt``, ``style``).  Static parameters like ``llmProvider`` and
    ``model`` are baked in at compile time via *defaults*.

    Args:
        name: Tool name (shown to the LLM).
        description: Human-readable description for the LLM.
        llm_provider: AI provider integration name (e.g. ``"openai"``).
        model: Model name (e.g. ``"dall-e-3"``).
        input_schema: JSON Schema for the LLM-provided parameters.
            If ``None``, a default schema with ``prompt``, ``style``,
            ``width``, and ``height`` is used.
        **defaults: Extra static parameters passed to the generation task
            (e.g. ``n=1``, ``outputFormat="png"``).

    Example::

        gen = image_tool(
            name="generate_image",
            description="Generate an image from a text description.",
            llm_provider="openai",
            model="dall-e-3",
        )

        agent = Agent(name="artist", model="openai/gpt-4o", tools=[gen])
    """
    if input_schema is None:
        input_schema = {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Text description of the image to generate.",
                },
                "style": {"type": "string", "description": "Image style: 'vivid' or 'natural'."},
                "width": {
                    "type": "integer",
                    "description": "Image width in pixels.",
                    "default": 1024,
                },
                "height": {
                    "type": "integer",
                    "description": "Image height in pixels.",
                    "default": 1024,
                },
                "size": {
                    "type": "string",
                    "description": "Image size (e.g. '1024x1024'). Alternative to width/height.",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of images to generate.",
                    "default": 1,
                },
                "outputFormat": {
                    "type": "string",
                    "description": "Output format: 'png', 'jpg', or 'webp'.",
                    "default": "png",
                },
                "weight": {"type": "number", "description": "Image weight parameter."},
            },
            "required": ["prompt"],
        }
    return _media_tool(
        "generate_image",
        "GENERATE_IMAGE",
        name,
        description,
        llm_provider,
        model,
        input_schema,
        **defaults,
    )


def audio_tool(
    name: str,
    description: str,
    llm_provider: str,
    model: str,
    input_schema: Optional[Dict[str, Any]] = None,
    **defaults: Any,
) -> ToolDef:
    """Create a tool that generates audio / text-to-speech (Conductor ``GENERATE_AUDIO`` task).

    No worker process is needed — the Conductor server calls the AI provider
    directly.

    Args:
        name: Tool name (shown to the LLM).
        description: Human-readable description for the LLM.
        llm_provider: AI provider integration name (e.g. ``"openai"``).
        model: Model name (e.g. ``"tts-1"``).
        input_schema: JSON Schema for the LLM-provided parameters.
            If ``None``, a default schema with ``text`` and ``voice`` is used.
        **defaults: Extra static parameters (e.g. ``speed=1.0``).

    Example::

        tts = audio_tool(
            name="text_to_speech",
            description="Convert text to spoken audio.",
            llm_provider="openai",
            model="tts-1",
        )
    """
    if input_schema is None:
        input_schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to convert to speech."},
                "voice": {
                    "type": "string",
                    "description": "Voice to use.",
                    "enum": ["alloy", "echo", "fable", "onyx", "nova", "shimmer"],
                    "default": "alloy",
                },
                "speed": {
                    "type": "number",
                    "description": "Speech speed multiplier (0.25 to 4.0).",
                    "default": 1.0,
                },
                "responseFormat": {
                    "type": "string",
                    "description": "Audio format: 'mp3', 'wav', 'opus', 'aac', or 'flac'.",
                    "default": "mp3",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of audio outputs to generate.",
                    "default": 1,
                },
            },
            "required": ["text"],
        }
    return _media_tool(
        "generate_audio",
        "GENERATE_AUDIO",
        name,
        description,
        llm_provider,
        model,
        input_schema,
        **defaults,
    )


def video_tool(
    name: str,
    description: str,
    llm_provider: str,
    model: str,
    input_schema: Optional[Dict[str, Any]] = None,
    **defaults: Any,
) -> ToolDef:
    """Create a tool that generates video (Conductor ``GENERATE_VIDEO`` task).

    No worker process is needed — the Conductor server calls the AI provider
    directly.  Video generation is typically async — the server submits the
    job and polls until the video is ready.

    Args:
        name: Tool name (shown to the LLM).
        description: Human-readable description for the LLM.
        llm_provider: AI provider integration name (e.g. ``"openai"``).
        model: Model name (e.g. ``"sora-2"``).
        input_schema: JSON Schema for the LLM-provided parameters.
            If ``None``, a default schema with ``prompt``, ``duration``,
            and ``style`` is used.
        **defaults: Extra static parameters (e.g. ``size="1280x720"``).

    Example::

        vid = video_tool(
            name="generate_video",
            description="Generate a short video from a text description.",
            llm_provider="openai",
            model="sora-2",
        )
    """
    if input_schema is None:
        input_schema = {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Text description of the video scene."},
                "inputImage": {
                    "type": "string",
                    "description": "Base64-encoded or URL image for image-to-video generation.",
                },
                "duration": {
                    "type": "integer",
                    "description": "Video duration in seconds.",
                    "default": 5,
                },
                "width": {
                    "type": "integer",
                    "description": "Video width in pixels.",
                    "default": 1280,
                },
                "height": {
                    "type": "integer",
                    "description": "Video height in pixels.",
                    "default": 720,
                },
                "fps": {"type": "integer", "description": "Frames per second.", "default": 24},
                "outputFormat": {
                    "type": "string",
                    "description": "Video format (e.g. 'mp4').",
                    "default": "mp4",
                },
                "style": {
                    "type": "string",
                    "description": "Video style (e.g. 'cinematic', 'natural').",
                },
                "motion": {
                    "type": "string",
                    "description": "Movement intensity (e.g. 'slow', 'normal', 'extreme').",
                },
                "seed": {"type": "integer", "description": "Seed for reproducibility."},
                "guidanceScale": {
                    "type": "number",
                    "description": "Prompt adherence strength (1.0 to 20.0).",
                },
                "aspectRatio": {
                    "type": "string",
                    "description": "Aspect ratio (e.g. '16:9', '1:1').",
                },
                "negativePrompt": {
                    "type": "string",
                    "description": "Description of what to exclude from the video.",
                },
                "personGeneration": {
                    "type": "string",
                    "description": "Controls for human figure generation.",
                },
                "resolution": {
                    "type": "string",
                    "description": "Quality level (e.g. '720p', '1080p').",
                },
                "generateAudio": {
                    "type": "boolean",
                    "description": "Whether to generate audio with the video.",
                },
                "size": {
                    "type": "string",
                    "description": "Video size specification (e.g. '1280x720').",
                },
                "n": {
                    "type": "integer",
                    "description": "Number of videos to generate.",
                    "default": 1,
                },
                "maxDurationSeconds": {
                    "type": "integer",
                    "description": "Maximum duration ceiling in seconds.",
                },
                "maxCostDollars": {
                    "type": "number",
                    "description": "Maximum cost limit in dollars.",
                },
            },
            "required": ["prompt"],
        }
    return _media_tool(
        "generate_video",
        "GENERATE_VIDEO",
        name,
        description,
        llm_provider,
        model,
        input_schema,
        **defaults,
    )


def pdf_tool(
    name: str = "generate_pdf",
    description: str = "Generate a PDF document from markdown text.",
    input_schema: Optional[Dict[str, Any]] = None,
    **defaults: Any,
) -> ToolDef:
    """Create a tool that generates PDFs from markdown (Conductor ``GENERATE_PDF`` task).

    No worker process or AI provider is needed — the Conductor server converts
    markdown to PDF directly.  Supports GitHub Flavored Markdown including
    headings, tables, code blocks, lists, blockquotes, images, and links.

    The LLM decides *when* to call this tool and provides the ``markdown``
    parameter.  Static parameters like ``pageSize`` and ``theme`` can be
    baked in via *defaults*.

    Args:
        name: Tool name (shown to the LLM).
        description: Human-readable description for the LLM.
        input_schema: JSON Schema for the LLM-provided parameters.
            If ``None``, a default schema with ``markdown`` and common
            formatting options is used.
        **defaults: Extra static parameters passed to the generation task
            (e.g. ``pageSize="LETTER"``, ``theme="compact"``).

    Example::

        pdf = pdf_tool()

        agent = Agent(
            name="report_writer",
            model="openai/gpt-4o",
            tools=[pdf],
            instructions="Write reports and generate PDFs.",
        )
    """
    if input_schema is None:
        input_schema = {
            "type": "object",
            "properties": {
                "markdown": {"type": "string", "description": "Markdown text to convert to PDF."},
                "pageSize": {
                    "type": "string",
                    "description": "Page size: A4, LETTER, LEGAL, A3, or A5.",
                    "default": "A4",
                },
                "theme": {
                    "type": "string",
                    "description": "Style preset: 'default' or 'compact'.",
                    "default": "default",
                },
                "baseFontSize": {
                    "type": "number",
                    "description": "Base font size in points.",
                    "default": 11,
                },
            },
            "required": ["markdown"],
        }
    config: Dict[str, Any] = {"taskType": "GENERATE_PDF"}
    config.update(defaults)
    return ToolDef(
        name=name,
        description=description,
        input_schema=input_schema,
        tool_type="generate_pdf",
        config=config,
    )


# ── RAG tool constructors ──────────────────────────────────────────────

RAG_TOOL_TYPES = frozenset({"rag_index", "rag_search"})


def index_tool(
    name: str,
    description: str,
    vector_db: str,
    index: str,
    embedding_model_provider: str,
    embedding_model: str,
    namespace: str = "default_ns",
    chunk_size: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
    dimensions: Optional[int] = None,
    input_schema: Optional[Dict[str, Any]] = None,
) -> ToolDef:
    """Create a tool that indexes documents into a vector database (Conductor ``LLM_INDEX_TEXT`` task).

    No worker process is needed — the Conductor server handles embedding
    generation and vector storage directly.

    The LLM decides *when* to call this tool and provides dynamic parameters
    (``text``, ``docId``, ``metadata``).  Static parameters like ``vectorDB``,
    ``index``, and embedding model are baked in at compile time.

    Args:
        name: Tool name (shown to the LLM).
        description: Human-readable description for the LLM.
        vector_db: Vector database type (e.g. ``"pgvectordb"``, ``"pineconedb"``, ``"mongodb_atlas"``).
        index: Collection/index name in the vector database.
        embedding_model_provider: Embedding provider (e.g. ``"openai"``).
        embedding_model: Embedding model name (e.g. ``"text-embedding-3-small"``).
        namespace: Namespace/partition within the index (default ``"default_ns"``).
        chunk_size: Optional chunk size for text splitting.
        chunk_overlap: Optional chunk overlap for text splitting.
        dimensions: Optional embedding dimensions override.
        input_schema: JSON Schema for the LLM-provided parameters.
            If ``None``, a default schema with ``text``, ``docId``, and
            ``metadata`` is used.

    Example::

        kb_index = index_tool(
            name="index_document",
            description="Add a document to the knowledge base.",
            vector_db="pgvectordb",
            index="product_docs",
            embedding_model_provider="openai",
            embedding_model="text-embedding-3-small",
        )

        agent = Agent(name="indexer", model="openai/gpt-4o", tools=[kb_index])
    """
    if input_schema is None:
        input_schema = {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "The text content to index."},
                "docId": {"type": "string", "description": "Unique document identifier."},
                "metadata": {
                    "type": "object",
                    "description": "Optional metadata to store with the document.",
                },
            },
            "required": ["text", "docId"],
        }
    config: Dict[str, Any] = {
        "taskType": "LLM_INDEX_TEXT",
        "vectorDB": vector_db,
        "namespace": namespace,
        "index": index,
        "embeddingModelProvider": embedding_model_provider,
        "embeddingModel": embedding_model,
    }
    if chunk_size is not None:
        config["chunkSize"] = chunk_size
    if chunk_overlap is not None:
        config["chunkOverlap"] = chunk_overlap
    if dimensions is not None:
        config["dimensions"] = dimensions
    return ToolDef(
        name=name,
        description=description,
        input_schema=input_schema,
        tool_type="rag_index",
        config=config,
    )


def search_tool(
    name: str,
    description: str,
    vector_db: str,
    index: str,
    embedding_model_provider: str,
    embedding_model: str,
    namespace: str = "default_ns",
    max_results: int = 5,
    dimensions: Optional[int] = None,
    input_schema: Optional[Dict[str, Any]] = None,
) -> ToolDef:
    """Create a tool that searches a vector database (Conductor ``LLM_SEARCH_INDEX`` task).

    No worker process is needed — the Conductor server handles embedding
    generation and vector search directly.

    The LLM decides *when* to call this tool and provides the ``query``
    parameter.  Static parameters like ``vectorDB``, ``index``, and
    embedding model are baked in at compile time.

    Args:
        name: Tool name (shown to the LLM).
        description: Human-readable description for the LLM.
        vector_db: Vector database type (e.g. ``"pgvectordb"``, ``"pineconedb"``, ``"mongodb_atlas"``).
        index: Collection/index name in the vector database.
        embedding_model_provider: Embedding provider (e.g. ``"openai"``).
        embedding_model: Embedding model name (e.g. ``"text-embedding-3-small"``).
        namespace: Namespace/partition within the index (default ``"default_ns"``).
        max_results: Maximum number of results to return (default 5).
        dimensions: Optional embedding dimensions override.
        input_schema: JSON Schema for the LLM-provided parameters.
            If ``None``, a default schema with ``query`` is used.

    Example::

        kb_search = search_tool(
            name="search_knowledge_base",
            description="Search the product documentation.",
            vector_db="pgvectordb",
            index="product_docs",
            embedding_model_provider="openai",
            embedding_model="text-embedding-3-small",
        )

        agent = Agent(name="assistant", model="openai/gpt-4o", tools=[kb_search])
    """
    if input_schema is None:
        input_schema = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query."},
            },
            "required": ["query"],
        }
    config: Dict[str, Any] = {
        "taskType": "LLM_SEARCH_INDEX",
        "vectorDB": vector_db,
        "namespace": namespace,
        "index": index,
        "embeddingModelProvider": embedding_model_provider,
        "embeddingModel": embedding_model,
        "maxResults": max_results,
    }
    if dimensions is not None:
        config["dimensions"] = dimensions
    return ToolDef(
        name=name,
        description=description,
        input_schema=input_schema,
        tool_type="rag_search",
        config=config,
    )



# ── Human interaction tool ──────────────────────────────────────────────


def wait_for_message_tool(
    name: str,
    description: str,
    batch_size: int = 1,
) -> ToolDef:
    """Create a tool that pauses execution until a workflow message is received
    (Conductor ``PULL_WORKFLOW_MESSAGES`` task).

    When the LLM calls this tool, the workflow dequeues up to *batch_size*
    messages from its Workflow Message Queue (WMQ).  The task stays
    ``IN_PROGRESS`` while the queue is empty and completes once messages
    arrive, returning them to the next LLM turn as tool output.

    No worker process is needed — the Conductor server handles the
    ``PULL_WORKFLOW_MESSAGES`` task directly.  Use
    :meth:`~agentspan.AgentRuntime.send_message` from outside the workflow to
    push a message into the queue.

    Args:
        name: Tool name (shown to the LLM).
        description: Human-readable description for the LLM.
        batch_size: Maximum number of messages to dequeue per invocation
            (server cap is 100, default 1).

    Example::

        listen = wait_for_message_tool(
            name="wait_for_message",
            description="Wait until a message is sent to this agent.",
        )

        agent = Agent(
            name="listener",
            model="openai/gpt-4o",
            tools=[listen],
            instructions="Call wait_for_message when you need to wait for input.",
        )

        # From the caller side:
        runtime.send_message(workflow_id, {"text": "hello"})
    """
    return ToolDef(
        name=name,
        description=description,
        input_schema={"type": "object", "properties": {}},
        tool_type="pull_workflow_messages",
        config={"batchSize": batch_size},
    )


def human_tool(
    name: str,
    description: str,
    input_schema: Optional[Dict[str, Any]] = None,
) -> ToolDef:
    """Create a tool that pauses execution for human input (Conductor ``HUMAN`` task).

    When the LLM calls this tool, the workflow pauses and presents the LLM's
    arguments to a human operator.  The human's response is returned as the
    tool output and the LLM continues with the next turn.

    No worker process is needed — the Conductor server handles the HUMAN task
    directly.  The server generates the response form schema and validation
    pipeline automatically.

    Args:
        name: Tool name (shown to the LLM).
        description: Human-readable description for the LLM.  This also
            appears as the prompt shown to the human operator.
        input_schema: JSON Schema for the LLM-provided parameters.
            If ``None``, a default schema with a ``question`` field is used.

    Example::

        ask_user = human_tool(
            name="ask_user",
            description="Ask the user a question and wait for their response.",
        )

        agent = Agent(
            name="assistant",
            model="openai/gpt-4o",
            tools=[ask_user, other_tool],
            instructions="When you need clarification, use ask_user.",
        )
    """
    if input_schema is None:
        input_schema = {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question or prompt to present to the human.",
                },
            },
            "required": ["question"],
        }
    return ToolDef(
        name=name,
        description=description,
        input_schema=input_schema,
        tool_type="human",
    )


# ── Agent-as-tool ──────────────────────────────────────────────────────


def agent_tool(
    agent: Any,
    name: Optional[str] = None,
    description: Optional[str] = None,
    retry_count: Optional[int] = None,
    retry_delay_seconds: Optional[int] = None,
    optional: Optional[bool] = None,
) -> ToolDef:
    """Wrap an :class:`Agent` as a callable tool (invoked as a sub-workflow).

    Unlike sub-agents which use handoff delegation, an agent tool is called
    inline by the parent LLM — like a function call. The child agent runs
    its own workflow and returns the result as a tool output.

    Args:
        agent: The Agent instance to wrap as a tool.
        name: Optional override name (defaults to the agent's name).
        description: Optional override description.
        retry_count: Number of retries on failure (default 2).  Set to ``0``
            for no retries.
        retry_delay_seconds: Seconds between retries with linear backoff
            (default 2).
        optional: When ``True`` (default), a permanently failed sub-workflow
            does not fail the parent — the coordinator continues with partial
            results.  Set to ``False`` for fail-fast behaviour.

    Returns:
        A :class:`ToolDef` with ``tool_type="agent_tool"``.

    Example::

        researcher = Agent(name="researcher", model="openai/gpt-4o",
                          tools=[search], instructions="Research topics.")
        manager = Agent(name="manager", model="openai/gpt-4o",
                       tools=[agent_tool(researcher)],
                       instructions="Delegate research tasks.")
    """
    agent_name = getattr(agent, "name", str(agent))
    config: dict = {"agent": agent}
    if retry_count is not None:
        config["retryCount"] = retry_count
    if retry_delay_seconds is not None:
        config["retryDelaySeconds"] = retry_delay_seconds
    if optional is not None:
        config["optional"] = optional
    return ToolDef(
        name=name or agent_name,
        description=description or f"Invoke the {agent_name} agent",
        input_schema={
            "type": "object",
            "properties": {
                "request": {
                    "type": "string",
                    "description": "The request or question to send to this agent.",
                }
            },
            "required": ["request"],
        },
        tool_type="agent_tool",
        config=config,
    )


# ── Utilities ───────────────────────────────────────────────────────────


def _try_worker_task(func: Callable[..., Any]) -> Optional[ToolDef]:
    """Try to build a :class:`ToolDef` from a ``@worker_task``-decorated function.

    Looks up *func* in conductor-python's ``_decorated_functions`` registry.
    Returns ``None`` if the function is not found or if conductor-python is not
    installed.
    """
    try:
        from conductor.client.automator.task_handler import _decorated_functions
    except ImportError:
        return None

    original = getattr(func, "__wrapped__", func)

    for (task_name, _domain), entry in _decorated_functions.items():
        if entry["func"] is original or entry["func"] is func:
            from agentspan.agents._internal.schema_utils import schema_from_function

            description = inspect.getdoc(original) or ""
            schemas = schema_from_function(original)
            return ToolDef(
                name=task_name,
                description=description,
                input_schema=schemas.get("input", {}),
                output_schema=schemas.get("output", {}),
                func=original,
                tool_type="worker",
            )
    return None


def get_tool_def(obj: Any) -> ToolDef:
    """Extract a :class:`ToolDef` from a ``@tool``-decorated function, a
    ``@worker_task``-decorated function, or a ``ToolDef`` instance.

    Raises:
        TypeError: If *obj* is not a recognised tool type.
    """
    if isinstance(obj, ToolDef):
        return obj
    if callable(obj) and hasattr(obj, "_tool_def"):
        return obj._tool_def  # type: ignore[union-attr]
    if callable(obj):
        td = _try_worker_task(obj)
        if td is not None:
            return td
    raise TypeError(
        f"Expected a @tool-decorated function, @worker_task function, or ToolDef, "
        f"got {type(obj).__name__}"
    )


def get_tool_defs(tools: List[Any]) -> List[ToolDef]:
    """Extract :class:`ToolDef` instances from a mixed list of tools."""
    return [get_tool_def(t) for t in tools]
