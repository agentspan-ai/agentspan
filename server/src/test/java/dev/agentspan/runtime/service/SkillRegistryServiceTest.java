/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License. See LICENSE file in the project root for details.
 */

package dev.agentspan.runtime.service;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Instant;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockMultipartFile;

import dev.agentspan.runtime.auth.RequestContext;
import dev.agentspan.runtime.auth.RequestContextHolder;
import dev.agentspan.runtime.auth.User;
import dev.agentspan.runtime.model.skill.SkillDetail;

class SkillRegistryServiceTest {

    @TempDir
    Path tempDir;

    @AfterEach
    void clearRequestContext() {
        RequestContextHolder.clear();
    }

    @Test
    void registeredSkillsAreVisibleOnlyToOwner() throws Exception {
        SkillRegistryService service =
                new SkillRegistryService(tempDir.toString(), 1024 * 1024, 1024 * 1024, 10 * 1024 * 1024, 100);
        String skillName = "owned-skill";
        String manifest = "{\"name\":\"" + skillName + "\"}";

        asUser("user-a");
        SkillDetail registered = service.register(manifest, packageFile(skillName));

        assertThat(registered.getOwnerId()).isEqualTo("user-a");
        assertThat(service.get(skillName, null).getName()).isEqualTo(skillName);

        asUser("user-b");
        assertThat(service.list(false)).extracting("name").doesNotContain(skillName);
        assertThatThrownBy(() -> service.get(skillName, null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Skill not found");

        asUser("user-a");
        assertThat(service.list(false)).extracting("name").contains(skillName);
    }

    @Test
    void deletingLatestVersionPromotesPreviousVersion() throws Exception {
        SkillRegistryService service =
                new SkillRegistryService(tempDir.toString(), 1024 * 1024, 1024 * 1024, 10 * 1024 * 1024, 100);
        String skillName = "versioned-skill";
        asUser("user-a");

        service.register("{\"name\":\"" + skillName + "\",\"version\":\"v1\"}", packageFile(skillName));
        service.register("{\"name\":\"" + skillName + "\",\"version\":\"v2\"}", packageFile(skillName));

        assertThat(service.get(skillName, null).getVersion()).isEqualTo("v2");

        service.delete(skillName, "v2");

        assertThat(service.get(skillName, null).getVersion()).isEqualTo("v1");
        assertThat(service.packageBytes(skillName, "v1")).isNotEmpty();
    }

    @Test
    void sameSkillNameUsesPerOwnerLatestAndPackageStorage() throws Exception {
        SkillRegistryService service =
                new SkillRegistryService(tempDir.toString(), 1024 * 1024, 1024 * 1024, 10 * 1024 * 1024, 100);
        String skillName = "shared-name-skill";

        asUser("user-a");
        SkillDetail userAV1 = service.register(
                "{\"name\":\"" + skillName + "\",\"version\":\"v1\"}", packageFile(skillName, "User A v1"));

        asUser("user-b");
        SkillDetail userBV2 = service.register(
                "{\"name\":\"" + skillName + "\",\"version\":\"v2\"}", packageFile(skillName, "User B v2"));
        assertThat(service.get(skillName, null).getVersion()).isEqualTo("v2");
        assertThat(service.list(false)).extracting("version").containsExactly("v2");
        assertThat(service.packageBytes(skillName, "v2")).isEqualTo(service.packageBytes(skillName, null));
        byte[] userBPackage = service.packageBytes(skillName, "v2");

        asUser("user-a");
        assertThat(service.get(skillName, null).getVersion()).isEqualTo("v1");
        assertThat(service.list(false)).extracting("version").containsExactly("v1");
        assertThat(service.packageBytes(skillName, "v1")).isEqualTo(service.packageBytes(skillName, null));
        assertThat(service.packageBytes(skillName, "v1")).isNotEqualTo(userBPackage);

        service.delete(skillName, "v1");
        assertThatThrownBy(() -> service.get(skillName, null))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("Skill not found");

        asUser("user-b");
        assertThat(service.get(skillName, null).getVersion()).isEqualTo("v2");
        assertThat(service.packageBytes(skillName, "v2")).isNotEmpty();
        assertThat(userAV1.getPackageFileHandleId()).isNotEqualTo(userBV2.getPackageFileHandleId());
    }

    @Test
    @SuppressWarnings("unchecked")
    void skillRefRawConfigIncludesParamsAndRegisteredCrossSkills() throws Exception {
        SkillRegistryService service =
                new SkillRegistryService(tempDir.toString(), 1024 * 1024, 1024 * 1024, 10 * 1024 * 1024, 100);
        asUser("user-a");

        service.register(
                "{\"name\":\"child-skill\",\"version\":\"v1\"}", packageFile("child-skill", "Child instructions"));
        service.register(
                "{\"name\":\"parent-skill\",\"version\":\"v1\"}",
                new MockMultipartFile(
                        "package",
                        "skill.zip",
                        "application/zip",
                        zip(Map.of(
                                "SKILL.md",
                                "---\n"
                                        + "name: parent-skill\n"
                                        + "params:\n"
                                        + "  mode:\n"
                                        + "    default: fast\n"
                                        + "---\n"
                                        + "# Parent\nUse the child-skill skill.\n",
                                "scripts/review.py",
                                "print('review')"))));

        Map<String, Object> raw = service.resolveRawConfig(
                Map.of("name", "parent-skill", "version", "v1", "params", Map.of("mode", "slow")));

        assertThat((String) raw.get("skillMd")).contains("[Skill Parameters]").contains("mode: slow");
        assertThat((Map<String, Object>) raw.get("params")).containsEntry("mode", "slow");
        Map<String, Object> refs = (Map<String, Object>) raw.get("crossSkillRefs");
        assertThat(refs).containsKey("child-skill");
        Map<String, Object> child = (Map<String, Object>) refs.get("child-skill");
        assertThat((String) child.get("skillMd")).contains("Child instructions");
        assertThat((Map<String, Object>) child.get("skillRef")).containsEntry("name", "child-skill");
    }

    @Test
    @SuppressWarnings("unchecked")
    void registeredCrossSkillRefsArePinnedAtRegistrationTime() throws Exception {
        SkillRegistryService service =
                new SkillRegistryService(tempDir.toString(), 1024 * 1024, 1024 * 1024, 10 * 1024 * 1024, 100);
        asUser("user-a");

        service.register(
                "{\"name\":\"child-skill\",\"version\":\"v1\"}", packageFile("child-skill", "Child version one"));
        service.register(
                "{\"name\":\"parent-skill\",\"version\":\"v1\"}",
                new MockMultipartFile(
                        "package",
                        "skill.zip",
                        "application/zip",
                        zip(Map.of(
                                "SKILL.md", "---\nname: parent-skill\n---\n# Parent\nUse the child-skill skill.\n"))));
        service.register(
                "{\"name\":\"child-skill\",\"version\":\"v2\"}", packageFile("child-skill", "Child version two"));

        Map<String, Object> raw = service.resolveRawConfig(Map.of("name", "parent-skill", "version", "v1"));
        Map<String, Object> refs = (Map<String, Object>) raw.get("crossSkillRefs");
        Map<String, Object> child = (Map<String, Object>) refs.get("child-skill");
        Map<String, Object> skillRef = (Map<String, Object>) child.get("skillRef");

        assertThat(skillRef).containsEntry("version", "v1");
        assertThat((String) child.get("skillMd")).contains("Child version one").doesNotContain("Child version two");
    }

    private static void asUser(String userId) {
        RequestContextHolder.set(RequestContext.builder()
                .requestId("request-" + userId)
                .user(new User(userId, userId, userId + "@example.com", userId))
                .createdAt(Instant.now())
                .build());
    }

    private static MockMultipartFile packageFile(String skillName) throws Exception {
        return packageFile(skillName, "Owned Skill");
    }

    private static MockMultipartFile packageFile(String skillName, String body) throws Exception {
        return new MockMultipartFile(
                "package",
                "skill.zip",
                "application/zip",
                zip(Map.of(
                        "SKILL.md", "---\nname: " + skillName + "\ndescription: Owned skill\n---\n# " + body + "\n")));
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
}
