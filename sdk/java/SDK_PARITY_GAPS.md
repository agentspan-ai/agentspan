# Java SDK — Parity Gaps vs Python SDK

Tracked during cross-SDK verification (2026-04-08).

---

## 1. Output schema `title` fields missing

**Status:** Known gap, cosmetic  
**Impact:** None — server does not use `title` for validation or routing

Java generates output type schema via reflection from a plain Java class.
Python derives it from a Pydantic model which automatically adds `title` to
each property and at the schema root.

**Java produces:**
```json
{
  "schema": {
    "type": "object",
    "properties": {
      "city": { "type": "string" }
    }
  },
  "className": "WeatherReport"
}
```

**Python produces:**
```json
{
  "schema": {
    "title": "WeatherReport",
    "type": "object",
    "properties": {
      "city": { "title": "City", "type": "string" }
    }
  },
  "className": "WeatherReport"
}
```

**Fix:** In `AgentConfigSerializer.serializeOutputType()`, capitalize each field
name and add it as `title` on the property map. Also add root-level `title`
from the class simple name.

---
