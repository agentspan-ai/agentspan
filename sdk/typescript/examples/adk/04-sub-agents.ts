/**
 * Google ADK Agent with Sub-Agents -- multi-agent orchestration.
 *
 * Demonstrates:
 *   - Defining specialist sub-agents with tools
 *   - A coordinator agent that routes to specialists via subAgents
 *   - The server normalizer maps subAgents to agents + strategy="handoff"
 *
 * Requirements:
 *   - npm install @google/adk zod
 *   - AGENTSPAN_SERVER_URL for agentspan path
 */

import { LlmAgent, FunctionTool } from '@google/adk';
import { z } from 'zod';
import { AgentRuntime } from '../../src/index.js';

const model = process.env.AGENTSPAN_LLM_MODEL ?? 'gemini-2.5-flash';

// ── Specialist tools ─────────────────────────────────────────────────

const searchFlights = new FunctionTool({
  name: 'search_flights',
  description: 'Search for available flights.',
  parameters: z.object({
    origin: z.string().describe('Departure city'),
    destination: z.string().describe('Arrival city'),
    date: z.string().describe('Travel date (YYYY-MM-DD)'),
  }),
  execute: async (args: { origin: string; destination: string; date: string }) => ({
    flights: [
      { airline: 'SkyLine', departure: '08:00', arrival: '11:30', price: '$320' },
      { airline: 'AirGlobe', departure: '14:00', arrival: '17:45', price: '$285' },
    ],
    route: `${args.origin} -> ${args.destination}`,
    date: args.date,
  }),
});

const searchHotels = new FunctionTool({
  name: 'search_hotels',
  description: 'Search for available hotels.',
  parameters: z.object({
    city: z.string().describe('City to search hotels in'),
    checkin: z.string().describe('Check-in date (YYYY-MM-DD)'),
    checkout: z.string().describe('Check-out date (YYYY-MM-DD)'),
  }),
  execute: async (args: { city: string; checkin: string; checkout: string }) => ({
    hotels: [
      { name: 'Grand Plaza', rating: 4.5, price: '$180/night' },
      { name: 'City Comfort Inn', rating: 4.0, price: '$95/night' },
      { name: 'Boutique Lux', rating: 4.8, price: '$250/night' },
    ],
    city: args.city,
    dates: `${args.checkin} to ${args.checkout}`,
  }),
});

const getTravelAdvisory = new FunctionTool({
  name: 'get_travel_advisory',
  description: 'Get travel advisory information for a country.',
  parameters: z.object({
    country: z.string().describe('Country name'),
  }),
  execute: async (args: { country: string }) => {
    const advisories: Record<string, { level: string; visa: string }> = {
      japan: { level: 'Level 1 - Exercise Normal Precautions', visa: 'Visa-free for 90 days' },
      france: { level: 'Level 2 - Exercise Increased Caution', visa: 'Schengen visa required' },
      australia: { level: 'Level 1 - Exercise Normal Precautions', visa: 'eVisitor visa required' },
    };
    return advisories[args.country.toLowerCase()] ?? { level: 'Unknown', visa: 'Check embassy website' };
  },
});

// ── Specialist agents ────────────────────────────────────────────────

export const flightAgent = new LlmAgent({
  name: 'flight_specialist',
  model,
  description: 'Handles flight searches and booking inquiries.',
  instruction:
    'You are a flight specialist. Search for flights and present ' +
    'options clearly with prices and schedules.',
  tools: [searchFlights],
});

export const hotelAgent = new LlmAgent({
  name: 'hotel_specialist',
  model,
  description: 'Handles hotel searches and accommodation inquiries.',
  instruction:
    'You are a hotel specialist. Search for hotels and present ' +
    'options with ratings and prices.',
  tools: [searchHotels],
});

export const advisoryAgent = new LlmAgent({
  name: 'travel_advisory_specialist',
  model,
  description: 'Provides travel advisories, visa requirements, and safety information.',
  instruction:
    'You are a travel advisory specialist. Provide safety levels ' +
    'and visa requirements for destinations.',
  tools: [getTravelAdvisory],
});

// ── Coordinator agent ────────────────────────────────────────────────

export const coordinator = new LlmAgent({
  name: 'travel_coordinator',
  model,
  instruction:
    'You are a travel planning coordinator. When a user wants to plan a trip:\n' +
    '1. Use the travel advisory specialist to check safety and visa info\n' +
    '2. Use the flight specialist to find flights\n' +
    '3. Use the hotel specialist to find accommodation\n' +
    'Route the user\'s request to the appropriate specialist.',
  subAgents: [flightAgent, hotelAgent, advisoryAgent],
});

// ── Run on agentspan ───────────────────────────────────────────────

async function main() {
  const runtime = new AgentRuntime();
  try {
    // Deploy to server. CLI alternative (recommended for CI/CD):
    //   agentspan deploy <module>
    // await runtime.deploy(coordinator);
    // await runtime.serve(coordinator);
    // Direct run for local development:
    const result = await runtime.run(
    coordinator,
    'I want to plan a trip to Japan. I need a flight from San Francisco ' +
    'on 2025-04-15 and a hotel for 5 nights. Also, what\'s the travel advisory?',
    );
    console.log('Status:', result.status);
    result.printResult();
  } finally {
    await runtime.shutdown();
  }
}

// Only run when executed directly (not when imported for discovery)
if (process.argv[1]?.endsWith('04-sub-agents.ts') || process.argv[1]?.endsWith('04-sub-agents.js')) {
  main().catch(console.error);
}
