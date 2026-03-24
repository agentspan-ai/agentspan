/**
 * Shared types for the validation framework.
 */

import type { AgentEvent } from '../src/types.js';
import type { AlgorithmicChecks } from './checks/algorithmic.js';

/**
 * Result of validating a single example.
 */
export interface ValidationResult {
  example: string;
  status: 'PASS' | 'FAIL' | 'WARN';
  duration: number;
  checks: AlgorithmicChecks;
  judgeScore?: number;
  judgeReason?: string;
  comparisonScore?: number;
  comparisonReason?: string;
  output: string;
  events: AgentEvent[];
  error?: string;
}
