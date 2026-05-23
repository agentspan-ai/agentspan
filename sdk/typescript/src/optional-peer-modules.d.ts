declare module "ai" {
  export const generateText: (...args: unknown[]) => Promise<unknown>;
  export const streamText: (...args: unknown[]) => Promise<unknown>;
  const moduleExports: Record<string, unknown>;
  export default moduleExports;
}

declare module "@langchain/core/language_models/chat_models" {
  export class BaseChatModel {
    invoke(...args: unknown[]): Promise<unknown>;
  }
}
