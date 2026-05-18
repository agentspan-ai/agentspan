import { ApiSearchModal } from "components/v1/ApiSearchModal/ApiSearchModal";
import { curlHeaders } from "shared/CodeModal/curlHeader";
import { toCodeT, useParamsToSdk } from "shared/CodeModal/hook";
import { SupportedDisplayTypes } from "shared/CodeModal/types";

export type BuildQueryOutput = {
  agentName: string;
  prompt: string;
};

interface RunWorkflowApiSearchModalProps {
  buildQueryOutput: BuildQueryOutput;
  onClose: () => void;
}

const buildCurlCode = (
  buildQueryOutput: BuildQueryOutput,
  accessToken: string,
) => {
  const { agentName, prompt } = buildQueryOutput;

  const headers = {
    ...curlHeaders(accessToken),
    "Content-Type": "application/json",
  };

  const curlCommand = `# Step 1: Fetch the agent definition
AGENT_DEF=$(curl -s '${window.location.origin}/api/metadata/workflow/${encodeURIComponent(agentName)}' \\${Object.entries(headers)
    .map(([key, value]) => `\n  -H '${key}: ${value}' \\`)
    .join("")}
)

# Step 2: Start the agent
curl '${window.location.origin}/api/agent/start' \\${Object.entries(headers)
    .map(([key, value]) => `\n  -H '${key}: ${value}' \\`)
    .join("")}
  --data-raw "$(jq -n --argjson config "$AGENT_DEF" '{"agentConfig": $config, "prompt": ${JSON.stringify(prompt)}}')"`;

  return curlCommand;
};

const buildJsCode = (
  buildQueryOutput: BuildQueryOutput,
  accessToken: string,
) => {
  const { agentName, prompt } = buildQueryOutput;

  return `async function runAgent() {
  const baseUrl = "${window.location.origin}/api";
  const headers = {
    "Content-Type": "application/json",
    "X-Authorization": "${accessToken}",
  };

  // Step 1: Fetch the agent definition
  const defRes = await fetch(\`\${baseUrl}/metadata/workflow/${encodeURIComponent(agentName)}\`, { headers });
  const agentConfig = await defRes.json();

  // Step 2: Start the agent
  const res = await fetch(\`\${baseUrl}/agent/start\`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      agentConfig,
      prompt: ${JSON.stringify(prompt)},
    }),
  });

  const { executionId } = await res.json();
  return executionId;
}

runAgent();
`;
};

const toCodeMap: toCodeT<BuildQueryOutput> = {
  curl: buildCurlCode,
  javascript: buildJsCode,
};

const RunWorkflowApiSearchModal = ({
  onClose,
  buildQueryOutput,
}: RunWorkflowApiSearchModalProps) => {
  const { selectedLanguage, setSelectedLanguage, code } =
    useParamsToSdk<BuildQueryOutput>(buildQueryOutput, toCodeMap);

  return (
    <ApiSearchModal
      displayLanguage={selectedLanguage}
      handleClose={onClose}
      code={code}
      onTabChange={(val) => {
        setSelectedLanguage(val);
      }}
      dialogTitle="Run Agent API"
      dialogHeaderText="Here is the code for the run agent."
      languages={Object.keys(toCodeMap) as SupportedDisplayTypes[]}
    />
  );
};

export { RunWorkflowApiSearchModal };
