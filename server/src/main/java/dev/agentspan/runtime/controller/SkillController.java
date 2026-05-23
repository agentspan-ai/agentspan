/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.controller;

import java.util.List;
import java.util.Map;

import org.springframework.core.io.ByteArrayResource;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import dev.agentspan.runtime.model.StartRequest;
import dev.agentspan.runtime.model.StartResponse;
import dev.agentspan.runtime.model.skill.SkillDeployRequest;
import dev.agentspan.runtime.model.skill.SkillDetail;
import dev.agentspan.runtime.model.skill.SkillFileContent;
import dev.agentspan.runtime.model.skill.SkillSummary;
import dev.agentspan.runtime.service.AgentService;
import dev.agentspan.runtime.service.SkillRegistryService;

import lombok.RequiredArgsConstructor;

@Component
@RestController
@RequestMapping("/api/skills")
@RequiredArgsConstructor
public class SkillController {

    private final SkillRegistryService skillRegistryService;
    private final AgentService agentService;

    @PostMapping(value = "/register", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    public SkillDetail registerSkill(
            @RequestPart("manifest") String manifest, @RequestPart("package") MultipartFile packageFile) {
        return skillRegistryService.register(manifest, packageFile);
    }

    @GetMapping
    public List<SkillSummary> listSkills(@RequestParam(defaultValue = "false") boolean allVersions) {
        return skillRegistryService.list(allVersions);
    }

    @GetMapping("/{name}")
    public SkillDetail getLatestSkill(@PathVariable String name) {
        return skillRegistryService.get(name, null);
    }

    @GetMapping("/{name}/versions/{version}")
    public SkillDetail getSkill(@PathVariable String name, @PathVariable String version) {
        return skillRegistryService.get(name, version);
    }

    @GetMapping("/{name}/versions/{version}/files")
    public SkillFileContent readSkillFile(
            @PathVariable String name, @PathVariable String version, @RequestParam("path") String path) {
        return skillRegistryService.readFile(name, version, path);
    }

    @GetMapping("/{name}/versions/{version}/package")
    public ResponseEntity<ByteArrayResource> downloadSkillPackage(
            @PathVariable String name, @PathVariable String version) {
        byte[] bytes = skillRegistryService.packageBytes(name, version);
        String filename = name + "-" + version + ".zip";
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .contentLength(bytes.length)
                .header(
                        HttpHeaders.CONTENT_DISPOSITION,
                        ContentDisposition.attachment()
                                .filename(filename)
                                .build()
                                .toString())
                .body(new ByteArrayResource(bytes));
    }

    @PostMapping("/{name}/versions/{version}/deploy")
    public StartResponse deploySkill(
            @PathVariable String name,
            @PathVariable String version,
            @RequestBody(required = false) SkillDeployRequest request) {
        Map<String, Object> rawConfig = skillRegistryService.rawConfigForDeploy(
                name,
                version,
                request != null ? request.getModel() : null,
                request != null ? request.getAgentModels() : null);
        return agentService.deploy(StartRequest.builder()
                .framework("skill")
                .rawConfig(rawConfig)
                .skillRef(Map.of(
                        "name",
                        name,
                        "version",
                        skillRegistryService.get(name, version).getVersion()))
                .build());
    }

    @DeleteMapping("/{name}/versions/{version}")
    public ResponseEntity<Void> deleteSkill(@PathVariable String name, @PathVariable String version) {
        skillRegistryService.delete(name, version);
        return ResponseEntity.noContent().build();
    }
}
