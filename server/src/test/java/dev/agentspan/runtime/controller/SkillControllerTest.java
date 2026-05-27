/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;

import com.fasterxml.jackson.databind.ObjectMapper;

import dev.agentspan.runtime.AgentRuntime;

@SpringBootTest(classes = AgentRuntime.class)
@AutoConfigureMockMvc
@ActiveProfiles("test")
class SkillControllerTest {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    @Autowired
    private MockMvc mvc;

    @Test
    void registerListAndReadSkillFile() throws Exception {
        String name = "server-skill-" + System.nanoTime();
        byte[] zip = skillZip(
                name,
                Map.of(
                        "alpha-agent.md", "# Alpha\nAnalyze the request.",
                        "scripts/echo.py", "print('echo')",
                        "references/api.md", "# API"));

        mvc.perform(multipart("/api/skills/register")
                        .file(new MockMultipartFile("package", "skill.zip", "application/zip", zip))
                        .file(new MockMultipartFile(
                                "manifest",
                                "",
                                "application/json",
                                manifest(name, null).getBytes(StandardCharsets.UTF_8))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value(name))
                .andExpect(jsonPath("$.status").value("READY"))
                .andExpect(jsonPath("$.files[?(@.path=='SKILL.md')]").exists())
                .andExpect(jsonPath("$.files[?(@.path=='references/api.md')]").exists())
                .andExpect(jsonPath("$.rawConfig.skillMd", containsString("# Server Skill")))
                .andExpect(jsonPath("$.rawConfig.agentFiles.alpha", containsString("# Alpha")))
                .andExpect(jsonPath("$.rawConfig.scripts.echo.filename").value("echo.py"))
                .andExpect(jsonPath("$.rawConfig.resourceFiles[0]").value("references/api.md"));

        mvc.perform(get("/api/skills"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[?(@.name=='" + name + "')]").exists());

        mvc.perform(get("/api/skills/{name}", name))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value(name))
                .andExpect(jsonPath("$.rawConfig.skillMd", containsString("# Server Skill")));

        mvc.perform(get("/api/skills/{name}/versions/{version}/files", name, "latest")
                        .param("path", "references/api.md"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.content").value("# API"))
                .andExpect(jsonPath("$.binary").value(false));
    }

    @Test
    void registerDerivesRawConfigFromPackageAndIgnoresManifestRawConfig() throws Exception {
        String name = "derived-skill-" + System.nanoTime();
        byte[] zip = skillZip(name, Map.of("references/api.md", "# Trusted API"));
        Map<String, Object> maliciousRawConfig = new LinkedHashMap<>();
        maliciousRawConfig.put("model", "openai/gpt-4o");
        maliciousRawConfig.put(
                "skillMd", "---\nname: attacker-skill\n---\n# Manifest should not become registered instructions");
        maliciousRawConfig.put("resourceFiles", java.util.List.of("evil.txt"));

        Map<String, Object> manifest = new LinkedHashMap<>();
        manifest.put("name", name);
        manifest.put("rawConfig", maliciousRawConfig);

        mvc.perform(multipart("/api/skills/register")
                        .file(new MockMultipartFile("package", "skill.zip", "application/zip", zip))
                        .file(new MockMultipartFile(
                                "manifest", "", "application/json", MAPPER.writeValueAsBytes(manifest))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.name").value(name))
                .andExpect(jsonPath("$.rawConfig.skillMd", containsString("# Server Skill")))
                .andExpect(jsonPath("$.rawConfig.skillMd")
                        .value(org.hamcrest.Matchers.not(containsString("Manifest should not become registered"))))
                .andExpect(jsonPath("$.rawConfig.resourceFiles[0]").value("references/api.md"));
    }

    @Test
    void registerRejectsManifestNameMismatch() throws Exception {
        String name = "mismatch-skill-" + System.nanoTime();
        byte[] zip = skillZip(name, Map.of());

        mvc.perform(multipart("/api/skills/register")
                        .file(new MockMultipartFile("package", "skill.zip", "application/zip", zip))
                        .file(new MockMultipartFile(
                                "manifest",
                                "",
                                "application/json",
                                manifest("different-" + name, null).getBytes(StandardCharsets.UTF_8))))
                .andExpect(status().isBadRequest())
                .andExpect(content().string(containsString("does not match package SKILL.md name")));
    }

    @Test
    void registerRejectsUnsafeZipPath() throws Exception {
        String name = "unsafe-skill-" + System.nanoTime();
        byte[] zip = zip(Map.of("SKILL.md", skillMd(name), "../evil.txt", "bad"));

        mvc.perform(multipart("/api/skills/register")
                        .file(new MockMultipartFile("package", "skill.zip", "application/zip", zip))
                        .file(new MockMultipartFile(
                                "manifest",
                                "",
                                "application/json",
                                manifest(name, null).getBytes(StandardCharsets.UTF_8))))
                .andExpect(status().isBadRequest())
                .andExpect(content().string(containsString("Invalid skill package path")));
    }

    @Test
    void registerRejectsDuplicateNormalizedZipPath() throws Exception {
        String name = "duplicate-skill-" + System.nanoTime();
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(out)) {
            zip.putNextEntry(new ZipEntry("SKILL.md"));
            zip.write(skillMd(name).getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
            zip.putNextEntry(new ZipEntry("./SKILL.md"));
            zip.write(skillMd(name).getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }

        mvc.perform(multipart("/api/skills/register")
                        .file(new MockMultipartFile("package", "skill.zip", "application/zip", out.toByteArray()))
                        .file(new MockMultipartFile(
                                "manifest",
                                "",
                                "application/json",
                                manifest(name, null).getBytes(StandardCharsets.UTF_8))))
                .andExpect(status().isBadRequest())
                .andExpect(content().string(containsString("duplicate path")));
    }

    @Test
    void registerRejectsSkillMdWithoutFrontmatterName() throws Exception {
        String name = "frontmatter-skill-" + System.nanoTime();
        byte[] zip = zip(Map.of("SKILL.md", "# Missing frontmatter"));

        mvc.perform(multipart("/api/skills/register")
                        .file(new MockMultipartFile("package", "skill.zip", "application/zip", zip))
                        .file(new MockMultipartFile(
                                "manifest",
                                "",
                                "application/json",
                                manifest(name, null).getBytes(StandardCharsets.UTF_8))))
                .andExpect(status().isBadRequest())
                .andExpect(content().string(containsString("SKILL.md is missing required YAML frontmatter")));
    }

    @Test
    void compileCanResolveRegisteredSkillRef() throws Exception {
        String name = "compile-skill-" + System.nanoTime();
        byte[] zip = skillZip(name, Map.of());

        String registerResponse = mvc.perform(multipart("/api/skills/register")
                        .file(new MockMultipartFile("package", "skill.zip", "application/zip", zip))
                        .file(new MockMultipartFile(
                                "manifest",
                                "",
                                "application/json",
                                manifest(name, null).getBytes(StandardCharsets.UTF_8))))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();
        String version = MAPPER.readTree(registerResponse).get("version").asText();

        String body = MAPPER.writeValueAsString(Map.of(
                "framework",
                "skill",
                "skillRef",
                Map.of(
                        "name",
                        name,
                        "version",
                        version,
                        "model",
                        "openai/gpt-4o",
                        "workspace",
                        Map.of("enabled", true, "roots", List.of(Map.of("name", "workspace", "kind", "workspace"))))));

        mvc.perform(post("/api/agent/compile").contentType("application/json").content(body))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.workflowDef.name").value(name))
                .andExpect(jsonPath("$.workflowDef.metadata.agentDef.skillRef.name")
                        .value(name))
                .andExpect(jsonPath("$.workflowDef.metadata.agentDef.model").value("openai/gpt-4o"))
                .andExpect(jsonPath("$.workflowDef.metadata.agentDef.workspace.enabled")
                        .value(true))
                .andExpect(jsonPath("$.workflowDef.metadata.agentDef.workspace.roots[0].name")
                        .value("workspace"));
    }

    @Test
    void deleteSkillRemovesVersionAndPackageDownload() throws Exception {
        String name = "delete-skill-" + System.nanoTime();
        byte[] zip = skillZip(name, Map.of());

        String registerResponse = mvc.perform(multipart("/api/skills/register")
                        .file(new MockMultipartFile("package", "skill.zip", "application/zip", zip))
                        .file(new MockMultipartFile(
                                "manifest",
                                "",
                                "application/json",
                                manifest(name, "v1").getBytes(StandardCharsets.UTF_8))))
                .andExpect(status().isOk())
                .andReturn()
                .getResponse()
                .getContentAsString();
        String version = MAPPER.readTree(registerResponse).get("version").asText();

        mvc.perform(get("/api/skills/{name}/versions/{version}/package", name, version))
                .andExpect(status().isOk())
                .andExpect(content().bytes(zip));

        mvc.perform(delete("/api/skills/{name}/versions/{version}", name, version))
                .andExpect(status().isNoContent());

        mvc.perform(get("/api/skills/{name}/versions/{version}", name, version))
                .andExpect(status().isBadRequest())
                .andExpect(content().string(containsString("Skill not found")));
    }

    private static String manifest(String name, String version) throws Exception {
        Map<String, Object> manifest = new LinkedHashMap<>();
        manifest.put("name", name);
        manifest.put("version", version);
        manifest.put("description", "Server-side skill registry test");
        manifest.put("model", "");
        manifest.put("agentModels", Map.of());
        return MAPPER.writeValueAsString(manifest);
    }

    private static byte[] skillZip(String name, Map<String, String> extraFiles) throws Exception {
        Map<String, String> files = new LinkedHashMap<>();
        files.put("SKILL.md", skillMd(name));
        files.putAll(extraFiles);
        return zip(files);
    }

    private static byte[] zip(Map<String, String> files) throws Exception {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try (ZipOutputStream zip = new ZipOutputStream(out)) {
            for (Map.Entry<String, String> entry : files.entrySet()) {
                zip.putNextEntry(new ZipEntry(entry.getKey()));
                zip.write(entry.getValue().getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
        }
        return out.toByteArray();
    }

    private static String skillMd(String name) {
        return "---\nname: " + name
                + "\ndescription: Server-side skill registry test\n---\n# Server Skill\nUse these instructions.";
    }
}
