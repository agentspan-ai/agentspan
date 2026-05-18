import cloneDeep from "lodash/cloneDeep";

export const extractVariablesFromJSON = (data: Record<string, unknown>) => {
  const extractedVariables: Record<string, unknown> = {};

  const processObject = (obj: Record<string, unknown>, path = ""): void => {
    for (const [key, value] of Object.entries(obj)) {
      if (typeof value === "string") {
        for (const match of value.matchAll(/\$\{([^}]+)\}/g)) {
          const variableName = match[1];
          const keyName =
            path !== "" ? `${path.replace(/^\./, "")}.${key}` : key;
          extractedVariables[keyName] = variableName;
        }
      } else if (typeof value === "object" && value !== null) {
        processObject(value as Record<string, unknown>, `${path}.${key}`);
      }
    }
  };

  processObject(data);

  return extractedVariables;
};

const UNSUPPORTED_KEYWORDS = [
  "unevaluatedProperties",
  "unevaluatedItems",
  "dependentRequired",
  "dependentSchemas",
  "$anchor",
  "$dynamicAnchor",
  "$dynamicRef",
  "minContains",
  "maxContains",
] as const;

const NEWER_KEYWORDS = new Set<string>([...UNSUPPORTED_KEYWORDS, "$defs"]);

const DRAFT_7_URI = "http://json-schema.org/draft-07/schema#";

// Keys that contain nested schema objects to recurse into
const OBJECT_KEYS = ["properties", "patternProperties", "definitions"] as const;
const ARRAY_KEYS = ["allOf", "anyOf", "oneOf"] as const;
const SINGLE_KEYS = ["not", "if", "then", "else"] as const;

/**
 * Checks whether a schema object (or any nested descendant) uses
 * Draft 2019-09 / 2020-12 keywords that are not in Draft 7.
 */
const hasNewerKeywords = (obj: any): boolean => {
  if (obj == null || typeof obj !== "object") return false;

  if (Array.isArray(obj)) {
    return obj.some(hasNewerKeywords);
  }

  for (const kw of NEWER_KEYWORDS) {
    if (kw in obj) return true;
  }

  // Check inside schema-map keys (properties, patternProperties, definitions, $defs)
  for (const key of [...OBJECT_KEYS, "$defs"] as const) {
    const val = obj[key];
    if (val != null && typeof val === "object" && !Array.isArray(val)) {
      for (const k in val) {
        if (Object.prototype.hasOwnProperty.call(val, k) && hasNewerKeywords(val[k])) {
          return true;
        }
      }
    }
  }

  // Check inside array-of-schema keys
  for (const key of ARRAY_KEYS) {
    const val = obj[key];
    if (Array.isArray(val) && val.some(hasNewerKeywords)) return true;
  }

  // Check single-schema keys + items + additionalProperties
  for (const key of [...SINGLE_KEYS, "items", "additionalProperties"] as const) {
    const val = obj[key];
    if (val != null && typeof val === "object") {
      if (Array.isArray(val)) {
        if (val.some(hasNewerKeywords)) return true;
      } else {
        if (hasNewerKeywords(val)) return true;
      }
    }
  }

  return false;
};

/**
 * Recursively processes a schema node: converts $defs to definitions,
 * rewrites $ref paths, removes unsupported keywords, and recurses
 * into all nested schema positions.
 */
const processSchema = (node: any): any => {
  if (node == null || typeof node !== "object") return node;

  if (Array.isArray(node)) {
    return node.map(processSchema);
  }

  const obj: Record<string, any> = { ...node };

  // Convert $defs -> definitions
  if (obj.$defs != null && typeof obj.$defs === "object" && !Array.isArray(obj.$defs)) {
    obj.definitions =
      obj.definitions != null && typeof obj.definitions === "object" && !Array.isArray(obj.definitions)
        ? { ...obj.definitions, ...obj.$defs }
        : obj.$defs;
    delete obj.$defs;
  }

  // Rewrite $ref from $defs path to definitions path, remove external HTTP(S) refs
  if (typeof obj.$ref === "string" && obj.$ref.length > 0) {
    obj.$ref = obj.$ref.replace(/^#\/\$defs\//, "#/definitions/");
    if (obj.$ref.startsWith("http://") || obj.$ref.startsWith("https://")) {
      delete obj.$ref;
    }
  }

  // Remove unsupported keywords
  for (const kw of UNSUPPORTED_KEYWORDS) {
    if (kw in obj) delete obj[kw];
  }

  // Recurse into schema-map keys (properties, patternProperties, definitions)
  for (const key of OBJECT_KEYS) {
    const val = obj[key];
    if (val != null && typeof val === "object" && !Array.isArray(val)) {
      for (const k in val) {
        if (Object.prototype.hasOwnProperty.call(val, k) && val[k] != null) {
          val[k] = processSchema(val[k]);
        }
      }
    }
  }

  // Recurse into array-of-schema keys (allOf, anyOf, oneOf)
  for (const key of ARRAY_KEYS) {
    const val = obj[key];
    if (Array.isArray(val) && val.length > 0) {
      obj[key] = val.map(processSchema);
    }
  }

  // Recurse into single-schema keys (not, if, then, else)
  for (const key of SINGLE_KEYS) {
    if (obj[key] != null) {
      obj[key] = processSchema(obj[key]);
    }
  }

  // items: can be a single schema or an array of schemas
  if (obj.items != null) {
    if (Array.isArray(obj.items)) {
      if (obj.items.length > 0) {
        obj.items = obj.items.map(processSchema);
      }
    } else {
      obj.items = processSchema(obj.items);
    }
  }

  // additionalProperties: only recurse when it's a schema object (not a boolean)
  if (obj.additionalProperties != null && typeof obj.additionalProperties === "object" && !Array.isArray(obj.additionalProperties)) {
    obj.additionalProperties = processSchema(obj.additionalProperties);
  }

  return obj;
};

/**
 * Downgrades a JSON schema from newer versions (Draft 2019-09, Draft 2020-12) to Draft 7.
 * This function:
 * - Replaces $schema URI with Draft 7 URI
 * - Converts $defs to definitions
 * - Removes unsupported keywords (unevaluatedProperties, unevaluatedItems, etc.)
 *
 * @param schema - The JSON schema to downgrade
 * @returns A downgraded schema compatible with Draft 7, or an empty object if input is invalid
 */
export const downgradeSchemaToDraft7 = (
  schema: Record<string, any>,
): Record<string, any> => {
  // Handle null, undefined, non-objects
  if (schema == null || typeof schema !== "object") return {};
  // Return arrays as-is (not valid root schemas but preserve caller data)
  if (Array.isArray(schema)) return schema;

  try {
    const schemaVersion = schema.$schema;
    const isDraft07 =
      typeof schemaVersion === "string" &&
      schemaVersion.includes("draft-07");
    const hasHttpsUri =
      typeof schemaVersion === "string" &&
      schemaVersion.startsWith("https://");

    // Fast path: already Draft 7 with HTTP URI and no newer keywords anywhere
    if (isDraft07 && !hasHttpsUri && !hasNewerKeywords(schema)) {
      return schema;
    }

    // Deep clone to avoid mutating the original
    const downgraded: Record<string, any> =
      typeof structuredClone !== "undefined"
        ? structuredClone(schema)
        : cloneDeep(schema);

    // Always set $schema to Draft 7 HTTP URI
    downgraded.$schema = DRAFT_7_URI;

    return processSchema(downgraded);
  } catch {
    // If anything fails, return the original schema as a safe fallback
    return schema;
  }
};
