// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package org.conductoross.conductor.ai.tools;

import static org.junit.jupiter.api.Assertions.*;

import org.conductoross.conductor.ai.model.ToolDef;
import org.junit.jupiter.api.Test;

/** Pure unit tests for the tool builders — name + toolType wiring (no server). */
class ToolsTest {

    @Test
    void httpToolShape() {
        ToolDef t = HttpTool.builder()
                .name("fetch")
                .description("d")
                .url("http://x")
                .method("GET")
                .build();
        assertEquals("fetch", t.getName());
        assertEquals("http", t.getToolType());
    }

    @Test
    void httpToolRequiresName() {
        assertThrows(
                IllegalArgumentException.class,
                () -> HttpTool.builder().url("http://x").build());
    }

    @Test
    void mcpToolShape() {
        ToolDef t = McpTool.builder()
                .name("m")
                .description("d")
                .serverUrl("http://mcp")
                .build();
        assertEquals("mcp", t.getToolType());
        assertEquals("m", t.getName());
    }

    @Test
    void humanToolShape() {
        ToolDef t = HumanTool.create("ask", "d");
        assertEquals("human", t.getToolType());
        assertEquals("ask", t.getName());
    }

    @Test
    void pdfToolShape() {
        assertEquals("generate_pdf", PdfTool.create("p", "d").getToolType());
    }

    @Test
    void waitForMessageToolShape() {
        assertEquals(
                "pull_workflow_messages", WaitForMessageTool.create("w", "d").getToolType());
    }

    @Test
    void imageToolShape() {
        ToolDef t = MediaTools.imageTool("img", "d", "openai", "dall-e-3");
        assertEquals("img", t.getName());
        assertNotNull(t.getToolType());
    }
}
