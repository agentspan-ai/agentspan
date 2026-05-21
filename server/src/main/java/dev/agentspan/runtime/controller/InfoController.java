/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.controller;

import java.util.Map;
import java.util.UUID;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * GET /api/info — returns a per-JVM ``instance_id``.
 *
 * <p>The id is generated once when the bean is constructed and stays stable
 * for the life of the process. SDK clients use it to detect server restarts
 * and gate the boot-time credential sync — same id → already synced this
 * JVM, skip; different id → JVM is new, re-sync.</p>
 */
@RestController
@RequestMapping("/api/info")
public class InfoController {

    private final String instanceId = UUID.randomUUID().toString();

    @GetMapping
    public ResponseEntity<Map<String, String>> info() {
        return ResponseEntity.ok(Map.of("instance_id", instanceId));
    }
}
