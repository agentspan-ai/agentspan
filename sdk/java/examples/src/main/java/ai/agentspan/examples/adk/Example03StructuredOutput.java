// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agentspan;
import ai.agentspan.model.AgentResult;

import com.google.adk.agents.LlmAgent;
import com.google.genai.types.Schema;
import com.google.genai.types.Type;

import java.util.List;
import java.util.Map;

/**
 * Example Adk 03 — Structured Output
 *
 * <p>Java port of <code>sdk/python/examples/adk/03_structured_output.py</code>.
 *
 * <p>Demonstrates: enforced JSON schema response via native ADK's
 * {@code outputSchema(...)}. The schema is built from
 * {@code com.google.genai.types.Schema}.
 *
 * <p>Expected JSON output shape (mirrors the Python Pydantic models):
 * <pre>{@code
 * {
 *   "name": string,
 *   "servings": int,
 *   "prep_time_minutes": int,
 *   "cook_time_minutes": int,
 *   "ingredients": [
 *     {"name": string, "quantity": string, "unit": string}, ...
 *   ],
 *   "steps": [
 *     {"step_number": int, "instruction": string, "duration_minutes": int}, ...
 *   ],
 *   "difficulty": string
 * }
 * }</pre>
 */
public class Example03StructuredOutput {

    /** Mirrors Python's <code>Ingredient</code> Pydantic model. */
    public static class Ingredient {
        public String name;
        public String quantity;
        public String unit;
    }

    /** Mirrors Python's <code>RecipeStep</code> Pydantic model. */
    public static class RecipeStep {
        public int step_number;
        public String instruction;
        public int duration_minutes;
    }

    /** Mirrors Python's <code>Recipe</code> Pydantic model. */
    public static class Recipe {
        public String name;
        public int servings;
        public int prep_time_minutes;
        public int cook_time_minutes;
        public List<Ingredient> ingredients;
        public List<RecipeStep> steps;
        public String difficulty;
    }

    private static Schema strSchema() {
        return Schema.builder().type(Type.Known.STRING).build();
    }

    private static Schema intSchema() {
        return Schema.builder().type(Type.Known.INTEGER).build();
    }

    private static Schema recipeSchema() {
        Schema ingredient = Schema.builder()
            .type(Type.Known.OBJECT)
            .properties(Map.of(
                "name", strSchema(),
                "quantity", strSchema(),
                "unit", strSchema()
            ))
            .build();

        Schema step = Schema.builder()
            .type(Type.Known.OBJECT)
            .properties(Map.of(
                "step_number", intSchema(),
                "instruction", strSchema(),
                "duration_minutes", intSchema()
            ))
            .build();

        return Schema.builder()
            .type(Type.Known.OBJECT)
            .properties(Map.of(
                "name", strSchema(),
                "servings", intSchema(),
                "prep_time_minutes", intSchema(),
                "cook_time_minutes", intSchema(),
                "ingredients", Schema.builder().type(Type.Known.ARRAY).items(ingredient).build(),
                "steps", Schema.builder().type(Type.Known.ARRAY).items(step).build(),
                "difficulty", strSchema()
            ))
            .build();
    }

    public static void main(String[] args) {
        LlmAgent extractor = LlmAgent.builder()
            .name("recipe_generator")
            .description("Generates complete, structured recipes as JSON matching the Recipe schema.")
            .model(Settings.LLM_MODEL)
            .instruction("""
                You are a professional chef assistant. When asked for a recipe,
                provide a complete, well-structured recipe in JSON format with precise
                measurements, clear step-by-step instructions, and accurate timing.
                """)
            .outputSchema(recipeSchema())
            .build();

        // OpenAI's `json_object` response format requires the word "json" to
        // appear in the input messages. Gemini has no such constraint.
        AgentResult result = Agentspan.run(extractor,
            "Give me a recipe for classic Italian carbonara pasta. Return as JSON.");
        result.printResult();

        Agentspan.shutdown();
    }
}
