/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.net.URLEncoder;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.MessageDigest;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Base64;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.multipart.MultipartFile;
import org.yaml.snakeyaml.LoaderOptions;
import org.yaml.snakeyaml.Yaml;
import org.yaml.snakeyaml.constructor.SafeConstructor;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import dev.agentspan.runtime.auth.RequestContextHolder;
import dev.agentspan.runtime.model.skill.SkillDetail;
import dev.agentspan.runtime.model.skill.SkillFileContent;
import dev.agentspan.runtime.model.skill.SkillFileEntry;
import dev.agentspan.runtime.model.skill.SkillSummary;
import dev.agentspan.runtime.service.skill.FileSystemSkillPackageStore;
import dev.agentspan.runtime.service.skill.SkillPackageStore;
import dev.agentspan.runtime.service.skill.StoredSkillPackage;

@Component
public class SkillRegistryService {

    private static final ObjectMapper MAPPER = new ObjectMapper();
    private static final TypeReference<Map<String, Object>> MAP_TYPE = new TypeReference<>() {};
    private static final Pattern FRONTMATTER_PATTERN =
            Pattern.compile("^---\\s*\\R(.*?)\\R---\\s*\\R?(.*)", Pattern.DOTALL);
    private static final Pattern SKILL_NAME_PATTERN = Pattern.compile("[A-Za-z0-9._-]{1,128}");
    private static final Pattern VERSION_PATTERN = Pattern.compile("[A-Za-z0-9._+-]{1,128}");
    private static final Set<String> TEXT_EXTENSIONS = Set.of(
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".html",
            ".css",
            ".js",
            ".mjs",
            ".ts",
            ".tsx",
            ".jsx",
            ".py",
            ".sh",
            ".rb",
            ".go",
            ".java",
            ".kt",
            ".rs",
            ".toml",
            ".ini",
            ".properties",
            ".csv");

    private final Path storageRoot;
    private final long maxPackageBytes;
    private final long maxPreviewBytes;
    private final long maxUncompressedBytes;
    private final int maxFileCount;
    private final SkillPackageStore packageStore;

    @Autowired
    public SkillRegistryService(
            @Value("${agentspan.skills.storage.directory:${java.io.tmpdir}/agentspan/skills}") String storageDir,
            @Value("${agentspan.skills.max-package-bytes:52428800}") long maxPackageBytes,
            @Value("${agentspan.skills.max-preview-bytes:1048576}") long maxPreviewBytes,
            @Value("${agentspan.skills.max-uncompressed-bytes:209715200}") long maxUncompressedBytes,
            @Value("${agentspan.skills.max-file-count:2000}") int maxFileCount,
            SkillPackageStore packageStore) {
        this.storageRoot = Path.of(storageDir).toAbsolutePath().normalize();
        this.maxPackageBytes = maxPackageBytes;
        this.maxPreviewBytes = maxPreviewBytes;
        this.maxUncompressedBytes = maxUncompressedBytes;
        this.maxFileCount = maxFileCount;
        this.packageStore = packageStore;
    }

    public SkillRegistryService(
            String storageDir,
            long maxPackageBytes,
            long maxPreviewBytes,
            long maxUncompressedBytes,
            int maxFileCount) {
        this(
                storageDir,
                maxPackageBytes,
                maxPreviewBytes,
                maxUncompressedBytes,
                maxFileCount,
                new FileSystemSkillPackageStore(
                        Path.of(storageDir).resolve("packages").toString()));
    }

    public synchronized SkillDetail register(String manifestJson, MultipartFile packageFile) {
        if (packageFile == null || packageFile.isEmpty()) {
            throw new IllegalArgumentException("Skill package is required");
        }

        Map<String, Object> manifest = parseManifest(manifestJson);
        byte[] bytes = readPackage(packageFile);
        String checksum = sha256Hex(bytes);

        ParsedSkillPackage parsed = parseSkillPackage(bytes, manifest);
        String name = parsed.name();
        String ownerId = currentUserId();
        String manifestName = stringValue(manifest.get("name"));
        if (manifestName != null && !manifestName.isBlank() && !manifestName.equals(name)) {
            throw new IllegalArgumentException(
                    "Skill manifest name '" + manifestName + "' does not match package SKILL.md name '" + name + "'");
        }

        String version = stringValue(manifest.get("version"));
        if (version == null || version.isBlank()) {
            version = checksum.substring(0, 12);
        }
        validateVersion(version);

        long now = Instant.now().toEpochMilli();
        Path versionDir = versionDir(name, version);
        Path metadataPath = metadataPath(name, version);

        if (Files.exists(metadataPath)) {
            SkillDetail existing = readDetail(metadataPath);
            enforceReadable(existing);
            if (!checksum.equals(existing.getChecksum())) {
                throw new IllegalArgumentException(
                        "Skill " + name + " version " + version + " already exists with a different checksum");
            }
            if (!packageExists(existing)) {
                StoredSkillPackage restored = packageStore.store(name, version, checksum, bytes);
                existing.setPackageFileHandleId(restored.handle());
                existing.setStorageType(restored.storageType());
                existing.setPackageSize(restored.size());
                existing.setUpdatedAt(now);
                writeDetail(metadataPath, existing);
            }
            return existing;
        }

        StoredSkillPackage stored = null;
        try {
            Files.createDirectories(versionDir);
            stored = packageStore.store(name, version, checksum, bytes);

            SkillDetail detail = SkillDetail.builder()
                    .name(name)
                    .version(version)
                    .description(parsed.description())
                    .checksum(checksum)
                    .packageFileHandleId(stored.handle())
                    .storageType(stored.storageType())
                    .status("READY")
                    .ownerId(ownerId)
                    .createdAt(now)
                    .updatedAt(now)
                    .packageSize(stored.size())
                    .fileCount(parsed.files().size())
                    .files(parsed.files())
                    .metadata(parsed.metadata())
                    .rawConfig(parsed.rawConfig())
                    .build();
            writeDetail(metadataPath, detail);
            Files.writeString(latestPath(name), version, StandardCharsets.UTF_8);
            return detail;
        } catch (IOException e) {
            if (stored != null) {
                packageStore.delete(stored.handle());
            }
            throw new IllegalStateException("Failed to store skill package: " + e.getMessage(), e);
        } catch (RuntimeException e) {
            if (stored != null) {
                packageStore.delete(stored.handle());
            }
            throw e;
        }
    }

    public List<SkillSummary> list(boolean allVersions) {
        if (!Files.isDirectory(storageRoot)) {
            return List.of();
        }
        List<SkillSummary> summaries = new ArrayList<>();
        try (var skillDirs = Files.list(storageRoot)) {
            for (Path skillDir : skillDirs.filter(Files::isDirectory).toList()) {
                if (allVersions) {
                    try (var versions = Files.list(skillDir)) {
                        for (Path versionPath :
                                versions.filter(Files::isDirectory).toList()) {
                            addSummary(summaries, versionPath.resolve("metadata.json"));
                        }
                    }
                } else {
                    Path latest = skillDir.resolve("latest");
                    if (Files.exists(latest)) {
                        String version =
                                Files.readString(latest, StandardCharsets.UTF_8).trim();
                        addSummary(summaries, skillDir.resolve(encoded(version)).resolve("metadata.json"));
                    }
                }
            }
        } catch (IOException e) {
            throw new IllegalStateException("Failed to list skills: " + e.getMessage(), e);
        }
        summaries.sort(Comparator.comparing(SkillSummary::getName).thenComparing(SkillSummary::getVersion));
        return summaries;
    }

    public SkillDetail get(String name, String version) {
        String resolvedVersion = resolveVersion(name, version);
        Path metadataPath = metadataPath(name, resolvedVersion);
        if (!Files.exists(metadataPath)) {
            throw new IllegalArgumentException("Skill not found: " + name + "@" + resolvedVersion);
        }
        SkillDetail detail = readDetail(metadataPath);
        enforceReadable(detail);
        return detail;
    }

    public byte[] packageBytes(String name, String version) {
        SkillDetail detail = get(name, version);
        return packageBytes(detail);
    }

    public SkillFileContent readFile(String name, String version, String path) {
        if (path == null || path.isBlank()) {
            throw new IllegalArgumentException("File path is required");
        }
        String cleanPath = normalizeEntryName(path);
        SkillDetail detail = get(name, version);
        byte[] packageBytes = packageBytes(detail);
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(packageBytes))) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                if (entry.isDirectory()) {
                    continue;
                }
                String entryName = normalizeEntryName(entry.getName());
                if (!entryName.equals(cleanPath)) {
                    continue;
                }
                if (entry.getSize() > maxPreviewBytes) {
                    throw new IllegalArgumentException("Skill file is too large to preview: " + cleanPath);
                }
                byte[] data = readBounded(zip, maxPreviewBytes, "Skill file is too large to preview: " + cleanPath);
                boolean binary = isBinary(cleanPath, data);
                return SkillFileContent.builder()
                        .path(cleanPath)
                        .contentType(contentType(cleanPath))
                        .size(data.length)
                        .binary(binary)
                        .content(binary ? null : new String(data, StandardCharsets.UTF_8))
                        .contentBase64(binary ? Base64.getEncoder().encodeToString(data) : null)
                        .build();
            }
            throw new IllegalArgumentException("Skill file not found: " + cleanPath);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to read skill file: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    public Map<String, Object> resolveRawConfig(Map<String, Object> skillRef) {
        if (skillRef == null) {
            throw new IllegalArgumentException("skillRef is required");
        }
        String name = requiredString(skillRef, "name");
        String version = stringValue(skillRef.get("version"));
        SkillDetail detail = get(name, version);
        Map<String, Object> rawConfig = deepCopy(detail.getRawConfig());
        rawConfig.put(
                "skillRef",
                Map.of(
                        "name", detail.getName(),
                        "version", detail.getVersion(),
                        "checksum", detail.getChecksum()));
        Object model = skillRef.get("model");
        if (model instanceof String s && !s.isBlank()) {
            rawConfig.put("model", s);
        }
        Object agentModels = skillRef.get("agentModels");
        if (agentModels instanceof Map<?, ?> map && !map.isEmpty()) {
            rawConfig.put("agentModels", MAPPER.convertValue(map, Map.class));
        }
        Object workspace = skillRef.get("workspace");
        if (workspace instanceof Map<?, ?> map && !map.isEmpty()) {
            rawConfig.put("workspace", MAPPER.convertValue(map, Map.class));
        }
        return rawConfig;
    }

    public Map<String, Object> rawConfigForDeploy(
            String name, String version, String model, Map<String, String> agentModels) {
        SkillDetail detail = get(name, version);
        Map<String, Object> rawConfig = deepCopy(detail.getRawConfig());
        rawConfig.put(
                "skillRef",
                Map.of(
                        "name", detail.getName(),
                        "version", detail.getVersion(),
                        "checksum", detail.getChecksum()));
        if (model != null && !model.isBlank()) {
            rawConfig.put("model", model);
        }
        if (agentModels != null && !agentModels.isEmpty()) {
            rawConfig.put("agentModels", new LinkedHashMap<>(agentModels));
        }
        return rawConfig;
    }

    public synchronized void delete(String name, String version) {
        String resolvedVersion = resolveVersion(name, version);
        Path dir = versionDir(name, resolvedVersion);
        if (!Files.exists(dir)) {
            return;
        }
        Path metadataPath = metadataPath(name, resolvedVersion);
        SkillDetail detail = null;
        if (Files.exists(metadataPath)) {
            detail = readDetail(metadataPath);
            enforceReadable(detail);
        }
        try (var paths = Files.walk(dir)) {
            for (Path p : paths.sorted(Comparator.reverseOrder()).toList()) {
                Files.deleteIfExists(p);
            }
            if (detail != null) {
                deletePackage(detail);
            }
            Path latest = latestPath(name);
            if (Files.exists(latest)
                    && resolvedVersion.equals(
                            Files.readString(latest, StandardCharsets.UTF_8).trim())) {
                updateLatestAfterDelete(name);
            }
        } catch (IOException e) {
            throw new IllegalStateException("Failed to delete skill: " + e.getMessage(), e);
        }
    }

    private void addSummary(List<SkillSummary> summaries, Path metadataPath) {
        if (!Files.exists(metadataPath)) {
            return;
        }
        SkillDetail detail = readDetail(metadataPath);
        if (!isReadable(detail)) {
            return;
        }
        Map<String, Object> raw = detail.getRawConfig() != null ? detail.getRawConfig() : Map.of();
        summaries.add(SkillSummary.builder()
                .name(detail.getName())
                .version(detail.getVersion())
                .description(detail.getDescription())
                .checksum(detail.getChecksum())
                .status(detail.getStatus())
                .ownerId(detail.getOwnerId())
                .createdAt(detail.getCreatedAt())
                .updatedAt(detail.getUpdatedAt())
                .packageSize(detail.getPackageSize())
                .fileCount(detail.getFileCount())
                .scriptCount(sizeOf(raw.get("scripts")))
                .subAgentCount(sizeOf(raw.get("agentFiles")))
                .resourceCount(sizeOf(raw.get("resourceFiles")))
                .build());
    }

    private String resolveVersion(String name, String version) {
        if ("latest".equals(version)) {
            version = null;
        }
        if (version != null && !version.isBlank()) {
            Path direct = metadataPath(name, version);
            if (Files.exists(direct)) {
                return version;
            }
            Path skillRoot = skillRoot(name);
            if (Files.isDirectory(skillRoot)) {
                try (var versions = Files.list(skillRoot)) {
                    for (Path candidate : versions.filter(Files::isDirectory).toList()) {
                        SkillDetail detail = readDetail(candidate.resolve("metadata.json"));
                        if (detail.getChecksum() != null && detail.getChecksum().startsWith(version)) {
                            return detail.getVersion();
                        }
                    }
                } catch (IOException e) {
                    throw new IllegalStateException("Failed to resolve skill version: " + e.getMessage(), e);
                }
            }
            return version;
        }
        Path latest = latestPath(name);
        if (!Files.exists(latest)) {
            throw new IllegalArgumentException("Skill not found: " + name);
        }
        try {
            return Files.readString(latest, StandardCharsets.UTF_8).trim();
        } catch (IOException e) {
            throw new IllegalStateException("Failed to read latest skill version: " + e.getMessage(), e);
        }
    }

    private Map<String, Object> parseManifest(String manifestJson) {
        if (manifestJson == null || manifestJson.isBlank()) {
            throw new IllegalArgumentException("Skill manifest is required");
        }
        try {
            return MAPPER.readValue(manifestJson, MAP_TYPE);
        } catch (IOException e) {
            throw new IllegalArgumentException("Invalid skill manifest JSON: " + e.getMessage(), e);
        }
    }

    private byte[] readPackage(MultipartFile packageFile) {
        try {
            byte[] bytes = packageFile.getBytes();
            if (bytes.length > maxPackageBytes) {
                throw new IllegalArgumentException("Skill package exceeds max size of " + maxPackageBytes + " bytes");
            }
            return bytes;
        } catch (IOException e) {
            throw new IllegalArgumentException("Failed to read skill package: " + e.getMessage(), e);
        }
    }

    @SuppressWarnings("unchecked")
    private ParsedSkillPackage parseSkillPackage(byte[] bytes, Map<String, Object> manifest) {
        List<SkillFileEntry> files = new ArrayList<>();
        Map<String, byte[]> contentByPath = new TreeMap<>();
        long totalUncompressedBytes = 0;
        try (ZipInputStream zip = new ZipInputStream(new ByteArrayInputStream(bytes))) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                if (entry.isDirectory()) {
                    continue;
                }
                if (files.size() >= maxFileCount) {
                    throw new IllegalArgumentException("Skill package exceeds max file count of " + maxFileCount);
                }
                String path = normalizeEntryName(entry.getName());
                if (contentByPath.containsKey(path)) {
                    throw new IllegalArgumentException("Skill package contains duplicate path: " + path);
                }
                MessageDigest digest = MessageDigest.getInstance("SHA-256");
                long size = 0;
                ByteArrayOutputStream content = new ByteArrayOutputStream();
                byte[] buffer = new byte[8192];
                int read;
                while ((read = zip.read(buffer)) >= 0) {
                    digest.update(buffer, 0, read);
                    content.write(buffer, 0, read);
                    size += read;
                    totalUncompressedBytes += read;
                    if (size > maxPackageBytes) {
                        throw new IllegalArgumentException("Skill package contains oversized file: " + path);
                    }
                    if (totalUncompressedBytes > maxUncompressedBytes) {
                        throw new IllegalArgumentException(
                                "Skill package exceeds max uncompressed size of " + maxUncompressedBytes + " bytes");
                    }
                }
                contentByPath.put(path, content.toByteArray());
                files.add(SkillFileEntry.builder()
                        .path(path)
                        .size(size)
                        .sha256(hex(digest.digest()))
                        .contentType(contentType(path))
                        .build());
            }
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException("Invalid skill package zip: " + e.getMessage(), e);
        }

        byte[] skillMdBytes = contentByPath.get("SKILL.md");
        if (skillMdBytes == null) {
            throw new IllegalArgumentException("Skill package is missing SKILL.md");
        }
        files.sort(Comparator.comparing(SkillFileEntry::getPath));

        String skillMd = decodeUtf8("SKILL.md", skillMdBytes);
        Map<String, Object> frontmatter = parseSkillFrontmatter(skillMd);
        String name = requiredString(frontmatter, "name");
        validateSkillName(name);
        String description = stringValue(frontmatter.get("description"));
        if (description == null || description.isBlank()) {
            description = stringValue(manifest.get("description"));
        }

        Map<String, String> agentFiles = new LinkedHashMap<>();
        Map<String, Map<String, Object>> scripts = new LinkedHashMap<>();
        List<String> resourceFiles = new ArrayList<>();

        for (String path : contentByPath.keySet()) {
            if (path.equals("SKILL.md")) {
                continue;
            }
            if (isRootAgentFile(path)) {
                agentFiles.put(
                        path.substring(0, path.length() - "-agent.md".length()),
                        decodeUtf8(path, contentByPath.get(path)));
                continue;
            }
            if (isScriptFile(path)) {
                String filename = path.substring("scripts/".length());
                String toolName = scriptToolName(filename);
                if (scripts.containsKey(toolName)) {
                    throw new IllegalArgumentException(
                            "Skill package contains duplicate script tool name: " + toolName);
                }
                Map<String, Object> info = new LinkedHashMap<>();
                info.put("filename", filename);
                info.put("language", detectScriptLanguage(filename));
                scripts.put(toolName, info);
                continue;
            }
            if (isResourceFile(path)) {
                resourceFiles.add(path);
            }
        }

        Map<String, Object> rawConfig = new LinkedHashMap<>();
        rawConfig.put("model", resolveModel(manifest));
        rawConfig.put("agentModels", resolveAgentModels(manifest));
        rawConfig.put("skillMd", skillMd);
        rawConfig.put("agentFiles", agentFiles);
        rawConfig.put("scripts", scripts);
        rawConfig.put("resourceFiles", resourceFiles);
        rawConfig.put("crossSkillRefs", Map.of());

        return new ParsedSkillPackage(
                name,
                description,
                mergeMetadata(toMap(frontmatter.get("metadata")), toMap(manifest.get("metadata"))),
                files,
                rawConfig);
    }

    private byte[] readBounded(InputStream in, long maxBytes, String errorMessage) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        byte[] buffer = new byte[8192];
        long total = 0;
        int read;
        while ((read = in.read(buffer)) >= 0) {
            total += read;
            if (total > maxBytes) {
                throw new IllegalArgumentException(errorMessage);
            }
            out.write(buffer, 0, read);
        }
        return out.toByteArray();
    }

    private Map<String, Object> parseSkillFrontmatter(String skillMd) {
        Matcher matcher = FRONTMATTER_PATTERN.matcher(skillMd);
        if (!matcher.matches()) {
            throw new IllegalArgumentException("SKILL.md is missing required YAML frontmatter");
        }
        try {
            LoaderOptions options = new LoaderOptions();
            Yaml yaml = new Yaml(new SafeConstructor(options));
            Object value = yaml.load(matcher.group(1));
            if (value == null) {
                return Map.of();
            }
            if (!(value instanceof Map<?, ?> map)) {
                throw new IllegalArgumentException("SKILL.md frontmatter must be a mapping");
            }
            return MAPPER.convertValue(map, MAP_TYPE);
        } catch (IllegalArgumentException e) {
            throw e;
        } catch (Exception e) {
            throw new IllegalArgumentException("Invalid SKILL.md frontmatter: " + e.getMessage(), e);
        }
    }

    private String decodeUtf8(String path, byte[] data) {
        try {
            return StandardCharsets.UTF_8
                    .newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(data))
                    .toString();
        } catch (CharacterCodingException e) {
            throw new IllegalArgumentException("Skill file must be UTF-8 text: " + path, e);
        }
    }

    private boolean isRootAgentFile(String path) {
        return !path.contains("/") && path.endsWith("-agent.md");
    }

    private boolean isScriptFile(String path) {
        if (!path.startsWith("scripts/")) {
            return false;
        }
        String filename = path.substring("scripts/".length());
        return !filename.isBlank() && !filename.contains("/");
    }

    private boolean isResourceFile(String path) {
        if (!path.contains("/")) {
            return true;
        }
        return path.startsWith("references/") || path.startsWith("examples/") || path.startsWith("assets/");
    }

    private String scriptToolName(String filename) {
        int dot = filename.lastIndexOf('.');
        if (dot > 0) {
            return filename.substring(0, dot);
        }
        return filename;
    }

    private String detectScriptLanguage(String filename) {
        String lower = filename.toLowerCase();
        if (lower.endsWith(".py")) return "python";
        if (lower.endsWith(".sh")) return "bash";
        if (lower.endsWith(".bat") || lower.endsWith(".cmd")) return "batch";
        if (lower.endsWith(".js") || lower.endsWith(".mjs") || lower.endsWith(".ts")) return "node";
        if (lower.endsWith(".rb")) return "ruby";
        if (lower.endsWith(".go")) return "go";
        return "bash";
    }

    @SuppressWarnings("unchecked")
    private String resolveModel(Map<String, Object> manifest) {
        String model = stringValue(manifest.get("model"));
        if (model != null) {
            return model;
        }
        Object rawConfig = manifest.get("rawConfig");
        if (rawConfig instanceof Map<?, ?> map) {
            model = stringValue(map.get("model"));
        }
        return model != null ? model : "";
    }

    @SuppressWarnings("unchecked")
    private Map<String, String> resolveAgentModels(Map<String, Object> manifest) {
        Object value = manifest.get("agentModels");
        if (!(value instanceof Map<?, ?>) && manifest.get("rawConfig") instanceof Map<?, ?> rawConfig) {
            value = rawConfig.get("agentModels");
        }
        if (!(value instanceof Map<?, ?> map)) {
            return Map.of();
        }
        Map<String, String> agentModels = new LinkedHashMap<>();
        for (Map.Entry<?, ?> entry : map.entrySet()) {
            if (entry.getKey() instanceof String key && entry.getValue() instanceof String model) {
                agentModels.put(key, model);
            }
        }
        return agentModels;
    }

    private Map<String, Object> mergeMetadata(
            Map<String, Object> packageMetadata, Map<String, Object> manifestMetadata) {
        if (packageMetadata.isEmpty()) {
            return manifestMetadata;
        }
        if (manifestMetadata.isEmpty()) {
            return packageMetadata;
        }
        Map<String, Object> merged = new LinkedHashMap<>(packageMetadata);
        merged.putAll(manifestMetadata);
        return merged;
    }

    private SkillDetail readDetail(Path metadataPath) {
        try {
            return MAPPER.readValue(metadataPath.toFile(), SkillDetail.class);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to read skill metadata: " + e.getMessage(), e);
        }
    }

    private void writeDetail(Path metadataPath, SkillDetail detail) {
        try {
            MAPPER.writerWithDefaultPrettyPrinter().writeValue(metadataPath.toFile(), detail);
        } catch (IOException e) {
            throw new IllegalStateException("Failed to write skill metadata: " + e.getMessage(), e);
        }
    }

    private boolean packageExists(SkillDetail detail) {
        String handle = detail.getPackageFileHandleId();
        if (handle != null && !handle.isBlank()) {
            try {
                if (packageStore.exists(handle)) {
                    return true;
                }
            } catch (RuntimeException ignored) {
                // Fall through to legacy package path lookup.
            }
        }
        return Files.exists(legacyPackagePath(detail.getName(), detail.getVersion()));
    }

    private byte[] packageBytes(SkillDetail detail) {
        String handle = detail.getPackageFileHandleId();
        if (handle != null && !handle.isBlank()) {
            try {
                return packageStore.read(handle);
            } catch (RuntimeException ignored) {
                // Fall through to legacy package path lookup.
            }
        }
        try {
            return Files.readAllBytes(legacyPackagePath(detail.getName(), detail.getVersion()));
        } catch (IOException e) {
            throw new IllegalArgumentException(
                    "Skill package not found: " + detail.getName() + "@" + detail.getVersion());
        }
    }

    private void deletePackage(SkillDetail detail) throws IOException {
        String handle = detail.getPackageFileHandleId();
        if (handle != null && !handle.isBlank()) {
            try {
                packageStore.delete(handle);
            } catch (IllegalArgumentException ignored) {
                // Legacy records used synthetic handles before the package store existed.
            }
        }
        Files.deleteIfExists(legacyPackagePath(detail.getName(), detail.getVersion()));
    }

    private void updateLatestAfterDelete(String name) throws IOException {
        Path skillRoot = skillRoot(name);
        if (!Files.isDirectory(skillRoot)) {
            Files.deleteIfExists(latestPath(name));
            return;
        }
        List<SkillDetail> remaining = new ArrayList<>();
        try (var versions = Files.list(skillRoot)) {
            for (Path versionPath : versions.filter(Files::isDirectory).toList()) {
                Path metadata = versionPath.resolve("metadata.json");
                if (Files.exists(metadata)) {
                    SkillDetail detail = readDetail(metadata);
                    if (isReadable(detail)) {
                        remaining.add(detail);
                    }
                }
            }
        }
        if (remaining.isEmpty()) {
            Files.deleteIfExists(latestPath(name));
            try (var children = Files.list(skillRoot)) {
                if (children.findAny().isEmpty()) {
                    Files.deleteIfExists(skillRoot);
                }
            }
            return;
        }
        remaining.sort(Comparator.comparing(SkillDetail::getCreatedAt, Comparator.nullsFirst(Long::compareTo))
                .thenComparing(SkillDetail::getVersion));
        Files.writeString(latestPath(name), remaining.get(remaining.size() - 1).getVersion(), StandardCharsets.UTF_8);
    }

    private String currentUserId() {
        return RequestContextHolder.get()
                .map(ctx -> ctx.getUser().getId())
                .orElse("00000000-0000-0000-0000-000000000000");
    }

    private boolean isReadable(SkillDetail detail) {
        String ownerId = detail.getOwnerId();
        return ownerId == null || ownerId.isBlank() || ownerId.equals(currentUserId());
    }

    private void enforceReadable(SkillDetail detail) {
        if (!isReadable(detail)) {
            throw new IllegalArgumentException("Skill not found: " + detail.getName() + "@" + detail.getVersion());
        }
    }

    private String normalizeEntryName(String name) {
        String normalized = name.replace('\\', '/');
        while (normalized.startsWith("./")) {
            normalized = normalized.substring(2);
        }
        if (normalized.isBlank() || normalized.startsWith("/") || normalized.contains("\0")) {
            throw new IllegalArgumentException("Invalid skill package path: " + name);
        }
        for (String part : normalized.split("/")) {
            if (part.isBlank() || ".".equals(part) || "..".equals(part)) {
                throw new IllegalArgumentException("Invalid skill package path: " + name);
            }
        }
        return normalized;
    }

    private Path skillRoot(String name) {
        return storageRoot.resolve(encoded(name));
    }

    private Path versionDir(String name, String version) {
        return skillRoot(name).resolve(encoded(version));
    }

    private Path metadataPath(String name, String version) {
        return versionDir(name, version).resolve("metadata.json");
    }

    private Path legacyPackagePath(String name, String version) {
        return versionDir(name, version).resolve("skill.zip");
    }

    private Path latestPath(String name) {
        return skillRoot(name).resolve("latest");
    }

    private String encoded(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    private void validateSkillName(String name) {
        if (!SKILL_NAME_PATTERN.matcher(name).matches()) {
            throw new IllegalArgumentException(
                    "Invalid skill name '" + name + "'. Use 1-128 characters: letters, numbers, '.', '_' or '-'.");
        }
    }

    private void validateVersion(String version) {
        if (!VERSION_PATTERN.matcher(version).matches()) {
            throw new IllegalArgumentException("Invalid skill version '" + version
                    + "'. Use 1-128 characters: letters, numbers, '.', '_', '+', or '-'.");
        }
    }

    private String sha256Hex(byte[] bytes) {
        try {
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            return hex(digest.digest(bytes));
        } catch (Exception e) {
            throw new IllegalStateException("SHA-256 digest is unavailable", e);
        }
    }

    private static String hex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }

    private static String requiredString(Map<String, Object> map, String key) {
        String value = stringValue(map.get(key));
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Missing required field: " + key);
        }
        return value;
    }

    private static String stringValue(Object value) {
        return value instanceof String s ? s : null;
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> toMap(Object value) {
        if (value instanceof Map<?, ?> map) {
            return MAPPER.convertValue(map, Map.class);
        }
        return Map.of();
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> deepCopy(Map<String, Object> value) {
        if (value == null) {
            return new LinkedHashMap<>();
        }
        return MAPPER.convertValue(value, Map.class);
    }

    private static int sizeOf(Object value) {
        if (value instanceof Map<?, ?> map) {
            return map.size();
        }
        if (value instanceof List<?> list) {
            return list.size();
        }
        return 0;
    }

    private static boolean isBinary(String path, byte[] data) {
        String lower = path.toLowerCase();
        if (TEXT_EXTENSIONS.stream().anyMatch(lower::endsWith)) {
            return false;
        }
        for (byte b : data) {
            if (b == 0) {
                return true;
            }
        }
        return false;
    }

    private static String contentType(String path) {
        String lower = path.toLowerCase();
        if (lower.endsWith(".md") || lower.endsWith(".txt")) return "text/plain";
        if (lower.endsWith(".json")) return "application/json";
        if (lower.endsWith(".yaml") || lower.endsWith(".yml")) return "application/yaml";
        if (lower.endsWith(".html") || lower.endsWith(".htm")) return "text/html";
        if (lower.endsWith(".css")) return "text/css";
        if (lower.endsWith(".js") || lower.endsWith(".mjs")) return "text/javascript";
        if (lower.endsWith(".png")) return "image/png";
        if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
        if (lower.endsWith(".gif")) return "image/gif";
        if (lower.endsWith(".svg")) return "image/svg+xml";
        return "application/octet-stream";
    }

    private record ParsedSkillPackage(
            String name,
            String description,
            Map<String, Object> metadata,
            List<SkillFileEntry> files,
            Map<String, Object> rawConfig) {}
}
