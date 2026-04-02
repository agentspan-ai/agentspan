#!/usr/bin/env node
/**
 * Reads an OpenAPI 3.x JSON spec and generates a TypeScript file
 * with API_CATEGORIES for the docs page.
 */
import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const specPath = process.argv[2] || resolve(__dirname, './api-docs.json');
const outPath = resolve(__dirname, 'src/docs/generated-api-data.ts');

const spec = JSON.parse(readFileSync(specPath, 'utf-8'));

// Collect endpoints grouped by tag
const tagMap = new Map();

for (const [path, methods] of Object.entries(spec.paths)) {
  for (const [method, op] of Object.entries(methods)) {
    if (typeof op !== 'object' || op === null) continue;
    const tags = op.tags || ['default'];
    for (const tag of tags) {
      if (!tagMap.has(tag)) tagMap.set(tag, []);

      const pathParams = [];
      const queryParams = [];
      for (const p of op.parameters || []) {
        const param = {
          name: p.name,
          type: p.schema?.type || 'string',
          required: p.required || false,
          description: p.description || '',
          example: p.schema?.example || p.example || '',
        };
        if (p.in === 'path') pathParams.push(param);
        else if (p.in === 'query') queryParams.push(param);
      }

      // Extract request body example
      let bodyExample = '';
      if (op.requestBody?.content) {
        const jsonContent = op.requestBody.content['application/json'];
        if (jsonContent?.example) {
          bodyExample = JSON.stringify(jsonContent.example, null, 2);
        } else if (jsonContent?.schema) {
          bodyExample = schemaToExample(jsonContent.schema, spec);
        }
      }

      // Extract response example
      let responseExample = '';
      const resp200 = op.responses?.['200'];
      if (resp200?.content?.['*/*']?.schema) {
        responseExample = schemaToExample(resp200.content['*/*'].schema, spec);
      } else if (resp200?.content?.['application/json']?.schema) {
        responseExample = schemaToExample(resp200.content['application/json'].schema, spec);
      }

      tagMap.get(tag).push({
        method: method.toUpperCase(),
        path,
        summary: op.summary || op.operationId || '',
        description: op.description || '',
        pathParams,
        queryParams,
        bodyExample,
        responseExample,
        hasBody: !!op.requestBody,
      });
    }
  }
}

function resolveRef(ref, spec) {
  const parts = ref.replace('#/', '').split('/');
  let obj = spec;
  for (const p of parts) obj = obj?.[p];
  return obj;
}

function schemaToExample(schema, spec, depth = 0) {
  if (depth > 3) return '';
  if (schema.$ref) {
    schema = resolveRef(schema.$ref, spec);
    if (!schema) return '';
  }
  if (schema.example) return JSON.stringify(schema.example, null, 2);

  if (schema.type === 'object' || schema.properties) {
    const obj = {};
    for (const [key, prop] of Object.entries(schema.properties || {})) {
      const resolved = prop.$ref ? resolveRef(prop.$ref, spec) : prop;
      if (!resolved) continue;
      if (resolved.example !== undefined) {
        obj[key] = resolved.example;
      } else if (resolved.type === 'string') {
        obj[key] = resolved.enum?.[0] || 'string';
      } else if (resolved.type === 'integer' || resolved.type === 'number') {
        obj[key] = 0;
      } else if (resolved.type === 'boolean') {
        obj[key] = false;
      } else if (resolved.type === 'array') {
        obj[key] = [];
      } else if (resolved.type === 'object' || resolved.properties) {
        try {
          obj[key] = JSON.parse(schemaToExample(resolved, spec, depth + 1) || '{}');
        } catch { obj[key] = {}; }
      } else {
        obj[key] = null;
      }
    }
    return JSON.stringify(obj, null, 2);
  }

  if (schema.type === 'array' && schema.items) {
    const itemExample = schemaToExample(schema.items, spec, depth + 1);
    if (itemExample) {
      try { return JSON.stringify([JSON.parse(itemExample)], null, 2); } catch {}
    }
    return '[]';
  }

  return '';
}

// Format tag name for display
function formatTagName(tag) {
  return tag
    .replace(/-/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase())
    .replace(/Resource$/, '')
    .replace(/Controller$/, '')
    .trim();
}

// Build output
const serverUrl = spec.servers?.[0]?.url || 'http://localhost:8080';

const categories = [];
for (const [tag, endpoints] of tagMap.entries()) {
  categories.push({
    name: formatTagName(tag),
    description: spec.tags?.find(t => t.name === tag)?.description || `${formatTagName(tag)} endpoints`,
    endpoints: endpoints.map(ep => ({
      method: ep.method,
      path: ep.path,
      summary: ep.summary,
      description: ep.description,
      pathParams: ep.pathParams.length > 0 ? ep.pathParams : undefined,
      queryParams: ep.queryParams.length > 0 ? ep.queryParams : undefined,
      bodyExample: ep.bodyExample || undefined,
      responseExample: ep.responseExample || undefined,
      tags: [tag],
    })),
  });
}

const output = `// Auto-generated from OpenAPI spec — do not edit manually
// Generated: ${new Date().toISOString()}
// Source: ${spec.info?.title || 'OpenAPI'} ${spec.info?.version || ''}

export const SERVER_URL = ${JSON.stringify(serverUrl)};

export const API_CATEGORIES = ${JSON.stringify(categories, null, 2)} as const;
`;

writeFileSync(outPath, output, 'utf-8');
console.log('Generated %d categories, %d endpoints → %s', categories.length, categories.reduce((s, c) => s + c.endpoints.length, 0), outPath);
