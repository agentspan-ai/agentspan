# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Unit tests for CLI_CREDENTIAL_MAP registry."""

import pytest

from agentspan.agents.runtime.credentials.cli_map import CLI_CREDENTIAL_MAP
from agentspan.agents.runtime.credentials.types import CredentialFile


class TestCliCredentialMap:
    """CLI_CREDENTIAL_MAP registry contents."""

    def test_gh_maps_to_github_tokens(self):
        assert "GITHUB_TOKEN" in CLI_CREDENTIAL_MAP["gh"]
        assert "GH_TOKEN" in CLI_CREDENTIAL_MAP["gh"]

    def test_git_maps_to_github_tokens(self):
        assert "GITHUB_TOKEN" in CLI_CREDENTIAL_MAP["git"]
        assert "GH_TOKEN" in CLI_CREDENTIAL_MAP["git"]

    def test_aws_maps_to_aws_keys(self):
        creds = CLI_CREDENTIAL_MAP["aws"]
        assert "AWS_ACCESS_KEY_ID" in creds
        assert "AWS_SECRET_ACCESS_KEY" in creds
        assert "AWS_SESSION_TOKEN" in creds

    def test_kubectl_maps_to_kubeconfig_file(self):
        creds = CLI_CREDENTIAL_MAP["kubectl"]
        assert any(
            isinstance(c, CredentialFile) and c.env_var == "KUBECONFIG"
            for c in creds
        )

    def test_helm_maps_to_kubeconfig_file(self):
        creds = CLI_CREDENTIAL_MAP["helm"]
        assert any(
            isinstance(c, CredentialFile) and c.env_var == "KUBECONFIG"
            for c in creds
        )

    def test_gcloud_maps_to_project_and_credentials_file(self):
        creds = CLI_CREDENTIAL_MAP["gcloud"]
        names = [c if isinstance(c, str) else c.env_var for c in creds]
        assert "GOOGLE_CLOUD_PROJECT" in names
        assert "GOOGLE_APPLICATION_CREDENTIALS" in names

    def test_az_maps_to_azure_vars(self):
        creds = CLI_CREDENTIAL_MAP["az"]
        assert "AZURE_CLIENT_ID" in creds
        assert "AZURE_CLIENT_SECRET" in creds
        assert "AZURE_TENANT_ID" in creds
        assert "AZURE_SUBSCRIPTION_ID" in creds

    def test_docker_maps_to_docker_creds(self):
        creds = CLI_CREDENTIAL_MAP["docker"]
        assert "DOCKER_USERNAME" in creds
        assert "DOCKER_PASSWORD" in creds

    def test_npm_maps_to_npm_token(self):
        assert "NPM_TOKEN" in CLI_CREDENTIAL_MAP["npm"]

    def test_cargo_maps_to_cargo_token(self):
        assert "CARGO_REGISTRY_TOKEN" in CLI_CREDENTIAL_MAP["cargo"]

    def test_terraform_maps_to_none(self):
        """terraform must explicitly map to None to trigger ConfigurationError at definition time."""
        assert "terraform" in CLI_CREDENTIAL_MAP
        assert CLI_CREDENTIAL_MAP["terraform"] is None

    def test_all_expected_keys_present(self):
        expected = {"gh", "git", "aws", "kubectl", "helm", "gcloud", "az", "docker",
                    "npm", "cargo", "terraform"}
        assert expected.issubset(set(CLI_CREDENTIAL_MAP.keys()))

    def test_kubeconfig_file_has_correct_relative_path(self):
        creds = CLI_CREDENTIAL_MAP["kubectl"]
        kubeconfig = next(
            c for c in creds if isinstance(c, CredentialFile) and c.env_var == "KUBECONFIG"
        )
        assert kubeconfig.relative_path == ".kube/config"

    def test_gcloud_credentials_file_has_correct_relative_path(self):
        creds = CLI_CREDENTIAL_MAP["gcloud"]
        gcloud_creds = next(
            c for c in creds
            if isinstance(c, CredentialFile)
            and c.env_var == "GOOGLE_APPLICATION_CREDENTIALS"
        )
        assert gcloud_creds.relative_path == ".config/gcloud/application_default_credentials.json"
