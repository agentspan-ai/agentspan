/**
 * Structured Output -- extracting structured data using withStructuredOutput.
 *
 * Demonstrates:
 *   - Using ChatOpenAI.withStructuredOutput() with Zod schemas
 *   - Extracting typed Person and Event data from unstructured text
 *   - RunnableSequence with prompt template and structured output
 *   - Running via AgentRuntime
 *
 * Requires: OPENAI_API_KEY environment variable
 */

import { ChatOpenAI } from '@langchain/openai';
import { ChatPromptTemplate } from '@langchain/core/prompts';
import { RunnableLambda } from '@langchain/core/runnables';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

// ── Zod schemas for structured extraction ────────────────

const PersonSchema = z.object({
  name: z.string().describe('Full name of the person'),
  age: z.number().nullable().describe('Age if mentioned, null otherwise'),
  occupation: z.string().nullable().describe('Job title or role, null if unknown'),
  location: z.string().nullable().describe('City or country, null if unknown'),
});

const PersonListSchema = z.object({
  people: z.array(PersonSchema).describe('List of people extracted from the text'),
  totalCount: z.number().describe('Total number of people found'),
});

const EventSchema = z.object({
  eventName: z.string().describe('Name of the event'),
  date: z.string().nullable().describe('Date of the event, null if unknown'),
  location: z.string().nullable().describe('Location of the event, null if unknown'),
  keyOutcomes: z.array(z.string()).describe('Key outcomes or announcements'),
});

// ── Extraction chains ────────────────────────────────────

const personExtractionPrompt = ChatPromptTemplate.fromMessages([
  ['system', 'Extract all people mentioned in the text. Return structured data with name, age, occupation, and location when available.'],
  ['human', '{input}'],
]);

const eventExtractionPrompt = ChatPromptTemplate.fromMessages([
  ['system', 'Extract event information from the text. Return the event name, date, location, and key outcomes.'],
  ['human', '{input}'],
]);

async function extractPeople(text: string) {
  const model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 });
  const structuredModel = model.withStructuredOutput(PersonListSchema);
  const chain = personExtractionPrompt.pipe(structuredModel);
  return chain.invoke({ input: text });
}

async function extractEvent(text: string) {
  const model = new ChatOpenAI({ modelName: 'gpt-4o-mini', temperature: 0 });
  const structuredModel = model.withStructuredOutput(EventSchema);
  const chain = eventExtractionPrompt.pipe(structuredModel);
  return chain.invoke({ input: text });
}

// ── Combined extraction as a runnable ────────────────────

async function extractAll(text: string): Promise<string> {
  const parts: string[] = [];

  try {
    const people = await extractPeople(text);
    if (people.totalCount > 0) {
      parts.push(`Found ${people.totalCount} person(s):`);
      for (const p of people.people) {
        const details = [p.name];
        if (p.age) details.push(`age ${p.age}`);
        if (p.occupation) details.push(p.occupation);
        if (p.location) details.push(`from ${p.location}`);
        parts.push(`  - ${details.join(', ')}`);
      }
    }
  } catch {
    // Text may not contain people
  }

  try {
    const event = await extractEvent(text);
    if (event.eventName) {
      parts.push(`\nEvent: ${event.eventName}`);
      if (event.date) parts.push(`Date:  ${event.date}`);
      if (event.location) parts.push(`Location: ${event.location}`);
      if (event.keyOutcomes.length > 0) {
        parts.push('Outcomes:');
        for (const o of event.keyOutcomes) {
          parts.push(`  - ${o}`);
        }
      }
    }
  } catch {
    // Text may not contain events
  }

  return parts.length > 0 ? parts.join('\n') : 'Could not extract structured information.';
}

const agentRunnable = new RunnableLambda({
  func: async (input: { input: string }) => {
    const output = await extractAll(input.input);
    return { output };
  },
});

// Add agentspan metadata for extraction
(agentRunnable as any)._agentspan = {
  model: 'openai/gpt-4o-mini',
  tools: [],
  framework: 'langchain',
};

async function main() {
  const runtime = new AgentRuntime();

  const texts = [
    "At yesterday's summit, Prime Minister Sarah Chen, 52, met with Tech CEO Marcus Rodriguez, " +
      '45, from San Francisco. The two discussed AI regulation. Dr. Yuki Tanaka, a 38-year-old ' +
      'economist from Tokyo, moderated the panel.',
    'The 2024 OpenAI DevDay took place in San Francisco on November 6th. Key announcements ' +
      'included GPT-4 Turbo, a new Assistants API with code interpreter and file handling, ' +
      'and significant price reductions across the API.',
  ];

  try {
    for (const text of texts) {
      console.log(`\n${'='.repeat(60)}`);
      console.log(`Text: ${text.slice(0, 80)}...`);

      const queryText = `Extract all information from this text: ${text}`;
      const result = await runtime.run(agentRunnable, queryText);
      console.log('Status:', result.status);
      result.printResult();
      console.log('-'.repeat(60));
    }
  } finally {
    await runtime.shutdown();
  }
}

main().catch(console.error);
