import type { GuardrailDef, GuardrailResult, Position, OnFail } from "./types.js";

// ── guardrail() function ─────────────────────────────────

export interface GuardrailOptions {
  name: string;
  position?: Position;
  onFail?: OnFail;
  maxRetries?: number;
}

/**
 * Wraps a function as a custom guardrail definition.
 *
 * Custom guardrails are registered as Conductor SIMPLE workers.
 * The worker receives the content to validate and returns GuardrailResult.
 */
export function guardrail(
  fn: (content: string) => GuardrailResult | Promise<GuardrailResult>,
  options: GuardrailOptions,
): GuardrailDef {
  const position = options.position ?? "output";
  const onFail = options.onFail ?? "raise";

  const def: GuardrailDef = {
    name: options.name,
    position,
    onFail,
    guardrailType: "custom",
    taskName: options.name,
    func: fn,
  };

  if (options.maxRetries !== undefined) {
    def.maxRetries = options.maxRetries;
  }

  return def;
}

// ── guardrail.external() — static method ─────────────────

export interface ExternalGuardrailOptions {
  name: string;
  position?: Position;
  onFail?: OnFail;
}

/**
 * Create an external guardrail definition (no local worker).
 * The task is dispatched to a remote worker.
 */
guardrail.external = function externalGuardrail(options: ExternalGuardrailOptions): GuardrailDef {
  return {
    name: options.name,
    position: options.position ?? "output",
    onFail: options.onFail ?? "raise",
    guardrailType: "external",
    taskName: options.name,
    func: null,
  };
};

// ── RegexGuardrail ───────────────────────────────────────

export interface RegexGuardrailOptions {
  name: string;
  patterns: string[];
  mode: "block" | "allow";
  position?: Position;
  onFail?: OnFail;
  message?: string;
  maxRetries?: number;
}

/**
 * Server-side regex guardrail — runs as INLINE JavaScript on the server.
 * No local worker is registered.
 *
 * - mode='block': fails if any pattern matches
 * - mode='allow': fails if no pattern matches
 */
export class RegexGuardrail {
  readonly name: string;
  readonly patterns: string[];
  readonly mode: "block" | "allow";
  readonly position: Position;
  readonly onFail: OnFail;
  readonly message?: string;
  readonly maxRetries: number;

  constructor(options: RegexGuardrailOptions) {
    this.name = options.name;
    this.patterns = options.patterns;
    this.mode = options.mode;
    this.position = options.position ?? "output";
    this.onFail = options.onFail ?? "raise";
    this.maxRetries = options.maxRetries ?? 3;
    if (options.message !== undefined) {
      this.message = options.message;
    }
  }

  /**
   * Convert to a GuardrailDef for serialization.
   */
  toGuardrailDef(): GuardrailDef {
    const def: GuardrailDef = {
      name: this.name,
      position: this.position,
      onFail: this.onFail,
      guardrailType: "regex",
      patterns: this.patterns,
      mode: this.mode,
      maxRetries: this.maxRetries,
    };

    if (this.message !== undefined) {
      def.message = this.message;
    }

    return def;
  }
}

// ── LLMGuardrail ─────────────────────────────────────────

export interface LLMGuardrailOptions {
  name: string;
  model: string;
  policy: string;
  position?: Position;
  onFail?: OnFail;
  maxRetries?: number;
  maxTokens?: number;
}

/**
 * Server-side LLM guardrail — runs as LLM_CHAT_COMPLETE on the server.
 * No local worker is registered.
 */
export class LLMGuardrail {
  readonly name: string;
  readonly model: string;
  readonly policy: string;
  readonly position: Position;
  readonly onFail: OnFail;
  readonly maxRetries: number;
  readonly maxTokens?: number;

  constructor(options: LLMGuardrailOptions) {
    this.name = options.name;
    this.model = options.model;
    this.policy = options.policy;
    this.position = options.position ?? "output";
    this.onFail = options.onFail ?? "raise";
    this.maxRetries = options.maxRetries ?? 3;
    if (options.maxTokens !== undefined) {
      this.maxTokens = options.maxTokens;
    }
  }

  /**
   * Convert to a GuardrailDef for serialization.
   */
  toGuardrailDef(): GuardrailDef {
    const def: GuardrailDef = {
      name: this.name,
      position: this.position,
      onFail: this.onFail,
      guardrailType: "llm",
      model: this.model,
      policy: this.policy,
      maxRetries: this.maxRetries,
    };

    if (this.maxTokens !== undefined) {
      def.maxTokens = this.maxTokens;
    }

    return def;
  }
}

// ── @Guardrail decorator ─────────────────────────────────

const GUARDRAIL_DECORATOR_KEY = Symbol("GUARDRAIL_DECORATOR");

export interface GuardrailDecoratorOptions {
  name?: string;
  position?: Position;
  onFail?: OnFail;
  maxRetries?: number;
}

/**
 * Class method decorator that marks a method as a guardrail.
 * Use `guardrailsFrom(instance)` to extract decorated methods as GuardrailDef[].
 */
export function Guardrail(options?: GuardrailDecoratorOptions) {
  return function (_target: object, propertyKey: string, descriptor: PropertyDescriptor): void {
    const metadata: GuardrailDecoratorOptions & { _methodName: string } = {
      ...options,
      _methodName: propertyKey,
    };

    if (!descriptor.value) return;

    Object.defineProperty(descriptor.value, GUARDRAIL_DECORATOR_KEY, {
      value: metadata,
      writable: false,
      enumerable: false,
      configurable: false,
    });
  };
}

/**
 * Extract all @Guardrail-decorated methods from a class instance as GuardrailDef[].
 * Each method is bound to the instance and wrapped as a custom guardrail.
 */
export function guardrailsFrom(instance: object): GuardrailDef[] {
  const defs: GuardrailDef[] = [];
  const proto = Object.getPrototypeOf(instance);
  const propertyNames = Object.getOwnPropertyNames(proto);

  for (const key of propertyNames) {
    if (key === "constructor") continue;
    const descriptor = Object.getOwnPropertyDescriptor(proto, key);
    if (!descriptor?.value || typeof descriptor.value !== "function") continue;

    const metadata = (descriptor.value as Record<symbol, unknown>)[GUARDRAIL_DECORATOR_KEY] as
      | (GuardrailDecoratorOptions & { _methodName: string })
      | undefined;

    if (!metadata) continue;

    const methodName = metadata._methodName;
    const boundFn = descriptor.value.bind(instance);

    const name = metadata.name ?? methodName;
    const position = metadata.position ?? "output";
    const onFail = metadata.onFail ?? "raise";

    const def: GuardrailDef = {
      name,
      position,
      onFail,
      guardrailType: "custom",
      taskName: name,
      func: boundFn,
    };

    if (metadata.maxRetries !== undefined) {
      def.maxRetries = metadata.maxRetries;
    }

    defs.push(def);
  }

  return defs;
}
