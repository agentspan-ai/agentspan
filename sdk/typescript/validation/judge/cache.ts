/**
 * SHA-based output caching for LLM judge results.
 *
 * Avoids redundant judge calls when the same example produces the same output
 * across runs. Uses SHA-256 hash (first 16 chars) of the output string.
 */

import * as crypto from 'node:crypto';
import * as fs from 'node:fs';
import * as path from 'node:path';

interface CacheEntry {
  score: number;
  reason: string;
}

interface CacheData {
  [exampleName: string]: {
    [outputHash: string]: CacheEntry;
  };
}

/**
 * Compute SHA-256 hash of a string, returning the first 16 hex chars.
 */
export function hashOutput(output: string): string {
  return crypto.createHash('sha256').update(output).digest('hex').slice(0, 16);
}

/**
 * Persistent cache for LLM judge scores, keyed by example name and output hash.
 */
export class JudgeCache {
  private data: CacheData;
  private readonly cachePath: string;

  constructor(cachePath: string) {
    this.cachePath = cachePath;
    this.data = {};

    // Load existing cache if present
    if (fs.existsSync(cachePath)) {
      try {
        const raw = fs.readFileSync(cachePath, 'utf-8');
        this.data = JSON.parse(raw) as CacheData;
      } catch {
        // Corrupted cache — start fresh
        this.data = {};
      }
    }
  }

  /**
   * Look up a cached score for the given example and output hash.
   * Returns null if not cached.
   */
  getScore(exampleName: string, outputHash: string): { score: number; reason: string } | null {
    const entry = this.data[exampleName]?.[outputHash];
    if (!entry) return null;
    return { score: entry.score, reason: entry.reason };
  }

  /**
   * Store a score in the cache.
   */
  setScore(exampleName: string, outputHash: string, score: number, reason: string): void {
    if (!this.data[exampleName]) {
      this.data[exampleName] = {};
    }
    this.data[exampleName][outputHash] = { score, reason };
  }

  /**
   * Write the cache to disk.
   */
  save(): void {
    const dir = path.dirname(this.cachePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
    fs.writeFileSync(this.cachePath, JSON.stringify(this.data, null, 2), 'utf-8');
  }
}
