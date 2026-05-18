// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package ai.agentspan.examples.adk;

import ai.agentspan.examples.Settings;

import ai.agentspan.Agent;
import ai.agentspan.Agentspan;
import ai.agentspan.frameworks.GoogleADKAgent;
import ai.agentspan.model.AgentResult;

import java.util.List;

/**
 * Example Adk 03 — Structured Output
 *
 * <p>Java port of <code>sdk/python/examples/adk/03_structured_output.py</code>.
 *
 * <p>Demonstrates: enforced JSON schema response via ADK's
 * {@code output_schema}. Java exposes this via {@code .outputType("Recipe")}
 * which the server normalizer maps to AgentConfig.outputType.
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

    public static void main(String[] args) {
        Agent agent = GoogleADKAgent.builder()
            .name("recipe_generator")
            .model(Settings.LLM_MODEL)
            .instruction(
                "You are a professional chef assistant. When asked for a recipe, "
                + "provide a complete, well-structured recipe with precise measurements, "
                + "clear step-by-step instructions, and accurate timing.")
            .outputType("Recipe")
            .build();

        AgentResult result = Agentspan.run(agent,
            "Give me a recipe for classic Italian carbonara pasta.");
        result.printResult();

        Agentspan.shutdown();
    }
}
