/**
 * JSON results persistence — save and load validation results.
 */

import * as fs from 'node:fs';
import * as path from 'node:path';
import type { ValidationResult } from '../types.js';

interface ResultsFile {
  timestamp: string;
  results: ValidationResult[];
}

/**
 * Save validation results to a JSON file in the output directory.
 *
 * Creates `<outputDir>/results.json` with a timestamp and the full results array.
 */
export function saveResults(results: ValidationResult[], outputDir: string): void {
  if (!fs.existsSync(outputDir)) {
    fs.mkdirSync(outputDir, { recursive: true });
  }

  const data: ResultsFile = {
    timestamp: new Date().toISOString(),
    results,
  };

  const filePath = path.join(outputDir, 'results.json');
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2), 'utf-8');
}

/**
 * Load validation results from a JSON file in the output directory.
 *
 * Returns an empty array if the file does not exist.
 */
export function loadResults(outputDir: string): ValidationResult[] {
  const filePath = path.join(outputDir, 'results.json');
  if (!fs.existsSync(filePath)) return [];

  try {
    const raw = fs.readFileSync(filePath, 'utf-8');
    const data = JSON.parse(raw) as ResultsFile;
    return data.results ?? [];
  } catch {
    return [];
  }
}
