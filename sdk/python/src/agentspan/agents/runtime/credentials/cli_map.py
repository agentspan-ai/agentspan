# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""CLI_CREDENTIAL_MAP — built-in registry mapping CLI tools to credential names.

``None`` entries (e.g. ``"terraform"``) indicate tools with no auto-mapping.
The ``Agent`` constructor raises ``ConfigurationError`` at definition time when
a ``None``-mapped tool is used without an explicit ``credentials=[...]`` list.

Enterprise module can extend this registry without modifying OSS code.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Union

from agentspan.agents.runtime.credentials.types import CredentialFile

# Each value is either:
#   - A list of str/CredentialFile  — auto-mapped credentials for this CLI tool
#   - None                          — no auto-mapping; raises ConfigurationError at Agent() time
CLI_CREDENTIAL_MAP: Dict[str, Optional[List[Union[str, CredentialFile]]]] = {
    "gh": ["GITHUB_TOKEN", "GH_TOKEN"],
    "git": ["GITHUB_TOKEN", "GH_TOKEN"],
    "aws": ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN"],
    "kubectl": [CredentialFile("KUBECONFIG", ".kube/config")],
    "helm": [CredentialFile("KUBECONFIG", ".kube/config")],
    "gcloud": [
        "GOOGLE_CLOUD_PROJECT",
        CredentialFile(
            "GOOGLE_APPLICATION_CREDENTIALS",
            ".config/gcloud/application_default_credentials.json",
        ),
    ],
    "az": [
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
    ],
    "docker": ["DOCKER_USERNAME", "DOCKER_PASSWORD"],
    "npm": ["NPM_TOKEN"],
    "cargo": ["CARGO_REGISTRY_TOKEN"],
    "terraform": None,  # No auto-mapping — raises ConfigurationError if no explicit credentials
}
