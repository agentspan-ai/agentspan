/*
 * Copyright (c) 2025 AgentSpan
 * Licensed under the MIT License.
 */
package dev.agentspan.runtime.architecture;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

import com.tngtech.archunit.core.importer.ImportOption;
import com.tngtech.archunit.junit.AnalyzeClasses;
import com.tngtech.archunit.junit.ArchTest;
import com.tngtech.archunit.lang.ArchRule;

import dev.agentspan.runtime.spi.CredentialStoreProvider;
import dev.agentspan.runtime.spi.ExecutionTokenIssuer;
import dev.agentspan.runtime.spi.MasterKeyProvider;
import dev.agentspan.runtime.spi.SecretOutputMasker;
import dev.agentspan.runtime.spi.SkillMetadataDAO;
import dev.agentspan.runtime.spi.SkillPackageStore;

/**
 * Library-purity check ("AgentSpan as a library" §9).
 *
 * <p>The {@code conductor-agentspan} library defines the SPI <b>interfaces</b> and the logic that
 * operates on them; the concrete store/crypto <b>implementations</b> are a host concern, living in
 * {@code conductor-agentspan-server} (OSS defaults) or in an embedding host (e.g. orkes-conductor).
 * These rules statically enforce that boundary on the library's own bytecode — they fail if a
 * concrete impl ever leaks back into the library.
 *
 * <p>Why ArchUnit and not {@code @SpringBootTest}: this is a claim about the <i>classes in the
 * jar</i>, not about bean wiring. Static analysis sees every class (including ones that are not
 * Spring beans); a context-boot test only sees what gets registered, and would merely re-derive the
 * module dependency graph that already forbids depending on the server.
 *
 * <p>Tests are excluded from the import ({@link ImportOption.DoNotIncludeTests}) so the in-test
 * fakes used elsewhere never count as violations.
 */
@AnalyzeClasses(packages = "dev.agentspan.runtime", importOptions = ImportOption.DoNotIncludeTests.class)
class LibraryPurityTest {

    /**
     * No class in the library may implement an SPI — implementations are contributed by the host.
     * This is the core of the dependency-inversion design.
     */
    @ArchTest
    static final ArchRule library_contains_no_spi_implementations = noClasses()
            .should()
            .implement(CredentialStoreProvider.class)
            .orShould()
            .implement(ExecutionTokenIssuer.class)
            .orShould()
            .implement(MasterKeyProvider.class)
            .orShould()
            .implement(SecretOutputMasker.class)
            .orShould()
            .implement(SkillMetadataDAO.class)
            .orShould()
            .implement(SkillPackageStore.class)
            .because("SPI implementations belong to a host module (conductor-agentspan-server / "
                    + "orkes-conductor); the library defines the interfaces only");

    /**
     * No class in the library may touch a persistence backend. Storage is behind the SPIs, and the
     * host that implements them brings the JDBC/connection-pool dependencies.
     */
    @ArchTest
    static final ArchRule library_does_not_depend_on_persistence_backends = noClasses()
            .should()
            .dependOnClassesThat()
            .resideInAnyPackage("javax.sql..", "org.springframework.jdbc..", "com.zaxxer.hikari..")
            .because("persistence backends belong to the host module that implements the storage "
                    + "SPIs, not the engine-neutral library");

    /**
     * No class in the library may perform cryptography — that belongs to host-supplied SPI impls
     * (the encrypted secret store behind {@code CredentialStoreProvider}, the HMAC token signer
     * behind {@code ExecutionTokenIssuer}).
     *
     * <p>The former Phase-1 exception for {@code ExecutionTokenService} is gone: its HMAC impl was
     * extracted to {@code HmacExecutionTokenIssuer} in the server, leaving the library crypto-free.
     */
    @ArchTest
    static final ArchRule library_does_not_perform_cryptography = noClasses()
            .should()
            .dependOnClassesThat()
            .resideInAnyPackage("javax.crypto..")
            .because("cryptography belongs to host-supplied SPI implementations "
                    + "(CredentialStoreProvider, ExecutionTokenIssuer), not the engine-neutral library");
}
