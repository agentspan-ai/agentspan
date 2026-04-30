// Copyright (c) 2025 Agentspan
// Licensed under the MIT License. See LICENSE file in the project root for details.

package dev.agentspan.discovery;

import dev.agentspan.Agent;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.lang.reflect.Field;
import java.lang.reflect.Modifier;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

/**
 * Agent and MCP tool discovery utilities.
 *
 * <pre>{@code
 * // Discover all Agent instances declared as static fields in given packages
 * List<Agent> agents = AgentDiscovery.discoverAgents("com.myapp.agents", "com.myapp.bots");
 * }</pre>
 */
public class AgentDiscovery {

    private static final Logger logger = LoggerFactory.getLogger(AgentDiscovery.class);
    private static final Map<String, List<Agent>> discoveryCache = new ConcurrentHashMap<>();

    private AgentDiscovery() {}

    /**
     * Scan packages for static {@link Agent} fields.
     *
     * @param packageNames dotted package names to scan (e.g. {@code "com.myapp.agents"})
     * @return list of discovered Agent instances, deduplicated by name
     */
    public static List<Agent> discoverAgents(String... packageNames) {
        Set<String> seen = new HashSet<>();
        List<Agent> discovered = new ArrayList<>();

        for (String pkg : packageNames) {
            String cacheKey = pkg;
            if (discoveryCache.containsKey(cacheKey)) {
                for (Agent a : discoveryCache.get(cacheKey)) {
                    if (seen.add(a.getName())) discovered.add(a);
                }
                continue;
            }

            List<Agent> pkgAgents = scanPackage(pkg);
            discoveryCache.put(cacheKey, pkgAgents);
            for (Agent a : pkgAgents) {
                if (seen.add(a.getName())) discovered.add(a);
            }
        }

        logger.info("Discovered {} agent(s) from packages {}: {}",
            discovered.size(), List.of(packageNames),
            discovered.stream().map(Agent::getName).collect(java.util.stream.Collectors.toList()));
        return discovered;
    }

    /**
     * Clear the MCP tool discovery cache so the next call re-scans servers.
     */
    public static void clearDiscoveryCache() {
        discoveryCache.clear();
        logger.debug("Discovery cache cleared");
    }

    private static List<Agent> scanPackage(String packageName) {
        List<Agent> agents = new ArrayList<>();
        try {
            ClassLoader cl = Thread.currentThread().getContextClassLoader();
            String path = packageName.replace('.', '/');

            // Scan classes in the package via the classloader
            var resources = cl.getResources(path);
            while (resources.hasMoreElements()) {
                var resource = resources.nextElement();
                if (resource.getProtocol().equals("file")) {
                    java.io.File dir = new java.io.File(resource.toURI());
                    scanDirectory(dir, packageName, cl, agents);
                }
            }
        } catch (Exception e) {
            logger.debug("Could not scan package '{}': {}", packageName, e.getMessage());
        }
        return agents;
    }

    private static void scanDirectory(java.io.File dir, String packageName,
            ClassLoader cl, List<Agent> agents) {
        if (!dir.exists()) return;
        for (java.io.File file : dir.listFiles()) {
            if (file.isDirectory()) {
                scanDirectory(file, packageName + "." + file.getName(), cl, agents);
            } else if (file.getName().endsWith(".class")) {
                String className = packageName + "." + file.getName().replace(".class", "");
                try {
                    Class<?> cls = cl.loadClass(className);
                    scanClass(cls, agents);
                } catch (Exception ignored) {}
            }
        }
    }

    private static void scanClass(Class<?> cls, List<Agent> agents) {
        for (Field field : cls.getDeclaredFields()) {
            if (!Agent.class.isAssignableFrom(field.getType())) continue;
            if (!Modifier.isStatic(field.getModifiers())) continue;
            try {
                field.setAccessible(true);
                Object value = field.get(null);
                if (value instanceof Agent) {
                    agents.add((Agent) value);
                }
            } catch (Exception ignored) {}
        }
    }
}
