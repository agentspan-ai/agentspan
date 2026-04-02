// Auto-generated from OpenAPI spec — do not edit manually
// Generated: 2026-04-02T08:54:52.000Z
// Source: OpenAPI definition v0

export const SERVER_URL = "http://localhost:6767";

export const API_CATEGORIES = [
  {
    "name": "Agent",
    "description": "Agent endpoints",
    "endpoints": [
      {
        "method": "PUT",
        "path": "/api/agent/{executionId}/resume",
        "summary": "resumeAgent",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "PUT",
        "path": "/api/agent/{executionId}/pause",
        "summary": "pauseAgent",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "PUT",
        "path": "/api/agent/executions/bulk/resume",
        "summary": "bulkResume",
        "description": "",
        "bodyExample": "[]",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "PUT",
        "path": "/api/agent/executions/bulk/pause",
        "summary": "bulkPause",
        "description": "",
        "bodyExample": "[]",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/{executionId}/tasks",
        "summary": "injectTask",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "bodyExample": "{\n  \"taskDefName\": \"string\",\n  \"referenceTaskName\": \"string\",\n  \"type\": \"string\",\n  \"inputData\": {},\n  \"status\": \"string\",\n  \"subWorkflowParam\": {\n    \"name\": \"string\",\n    \"version\": 0,\n    \"executionId\": \"string\"\n  }\n}",
        "responseExample": "{\n  \"taskId\": \"string\"\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/{executionId}/respond",
        "summary": "respondToAgent",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "bodyExample": "{}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/tasks/{executionId}/{refTaskName}/{status}",
        "summary": "updateTaskStatus",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          },
          {
            "name": "refTaskName",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          },
          {
            "name": "status",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "queryParams": [
          {
            "name": "workerid",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/start",
        "summary": "startAgent",
        "description": "",
        "bodyExample": "{\n  \"agentConfig\": {\n    \"name\": \"string\",\n    \"description\": \"string\",\n    \"model\": \"string\",\n    \"instructions\": {},\n    \"tools\": [],\n    \"agents\": [],\n    \"strategy\": \"string\",\n    \"router\": {},\n    \"outputType\": {\n      \"schema\": {},\n      \"className\": \"string\"\n    },\n    \"guardrails\": [],\n    \"memory\": {\n      \"messages\": [],\n      \"maxMessages\": 0\n    },\n    \"maxTurns\": 0,\n    \"maxTokens\": 0,\n    \"timeoutSeconds\": 0,\n    \"temperature\": 0,\n    \"stopWhen\": {\n      \"taskName\": \"string\"\n    },\n    \"termination\": {\n      \"type\": \"string\",\n      \"text\": \"string\",\n      \"caseSensitive\": false,\n      \"stopMessage\": \"string\",\n      \"maxMessages\": 0,\n      \"maxTotalTokens\": 0,\n      \"maxPromptTokens\": 0,\n      \"maxCompletionTokens\": 0,\n      \"conditions\": []\n    },\n    \"handoffs\": [],\n    \"callbacks\": [],\n    \"allowedTransitions\": {},\n    \"introduction\": \"string\",\n    \"metadata\": {},\n    \"codeExecution\": {\n      \"enabled\": false,\n      \"allowedLanguages\": [],\n      \"allowedCommands\": [],\n      \"timeout\": 0\n    },\n    \"cliConfig\": {\n      \"enabled\": false,\n      \"allowedCommands\": [],\n      \"timeout\": 0,\n      \"allowShell\": false\n    },\n    \"includeContents\": \"string\",\n    \"thinkingConfig\": {\n      \"enabled\": false,\n      \"budgetTokens\": 0\n    },\n    \"planner\": false,\n    \"requiredTools\": [],\n    \"gate\": {},\n    \"credentials\": [],\n    \"external\": false\n  },\n  \"prompt\": \"string\",\n  \"sessionId\": \"string\",\n  \"media\": [],\n  \"idempotencyKey\": \"string\",\n  \"credentials\": [],\n  \"framework\": \"string\",\n  \"rawConfig\": {},\n  \"timeoutSeconds\": 0\n}",
        "responseExample": "{\n  \"executionId\": \"string\",\n  \"agentName\": \"string\",\n  \"requiredWorkers\": []\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/executions/{executionId}/retry",
        "summary": "retryExecution",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "queryParams": [
          {
            "name": "resumeSubworkflowTasks",
            "type": "boolean",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/executions/{executionId}/restart",
        "summary": "restartExecution",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "queryParams": [
          {
            "name": "useLatestDefinitions",
            "type": "boolean",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/executions/{executionId}/rerun",
        "summary": "rerunExecution",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "bodyExample": "{\n  \"reRunFromWorkflowId\": \"string\",\n  \"workflowInput\": {},\n  \"reRunFromTaskId\": \"string\",\n  \"taskInput\": {},\n  \"correlationId\": \"string\"\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/executions/bulk/terminate",
        "summary": "bulkTerminate",
        "description": "",
        "queryParams": [
          {
            "name": "reason",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "bodyExample": "[]",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/executions/bulk/retry",
        "summary": "bulkRetry",
        "description": "",
        "bodyExample": "[]",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/executions/bulk/restart",
        "summary": "bulkRestart",
        "description": "",
        "queryParams": [
          {
            "name": "useLatestDefinitions",
            "type": "boolean",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "bodyExample": "[]",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/execution",
        "summary": "createTrackingExecution",
        "description": "",
        "bodyExample": "{\n  \"workflowName\": \"string\",\n  \"input\": {}\n}",
        "responseExample": "{\n  \"executionId\": \"string\"\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/events/{executionId}",
        "summary": "pushFrameworkEvent",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "bodyExample": "{}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/deploy",
        "summary": "deployAgent",
        "description": "",
        "bodyExample": "{\n  \"agentConfig\": {\n    \"name\": \"string\",\n    \"description\": \"string\",\n    \"model\": \"string\",\n    \"instructions\": {},\n    \"tools\": [],\n    \"agents\": [],\n    \"strategy\": \"string\",\n    \"router\": {},\n    \"outputType\": {\n      \"schema\": {},\n      \"className\": \"string\"\n    },\n    \"guardrails\": [],\n    \"memory\": {\n      \"messages\": [],\n      \"maxMessages\": 0\n    },\n    \"maxTurns\": 0,\n    \"maxTokens\": 0,\n    \"timeoutSeconds\": 0,\n    \"temperature\": 0,\n    \"stopWhen\": {\n      \"taskName\": \"string\"\n    },\n    \"termination\": {\n      \"type\": \"string\",\n      \"text\": \"string\",\n      \"caseSensitive\": false,\n      \"stopMessage\": \"string\",\n      \"maxMessages\": 0,\n      \"maxTotalTokens\": 0,\n      \"maxPromptTokens\": 0,\n      \"maxCompletionTokens\": 0,\n      \"conditions\": []\n    },\n    \"handoffs\": [],\n    \"callbacks\": [],\n    \"allowedTransitions\": {},\n    \"introduction\": \"string\",\n    \"metadata\": {},\n    \"codeExecution\": {\n      \"enabled\": false,\n      \"allowedLanguages\": [],\n      \"allowedCommands\": [],\n      \"timeout\": 0\n    },\n    \"cliConfig\": {\n      \"enabled\": false,\n      \"allowedCommands\": [],\n      \"timeout\": 0,\n      \"allowShell\": false\n    },\n    \"includeContents\": \"string\",\n    \"thinkingConfig\": {\n      \"enabled\": false,\n      \"budgetTokens\": 0\n    },\n    \"planner\": false,\n    \"requiredTools\": [],\n    \"gate\": {},\n    \"credentials\": [],\n    \"external\": false\n  },\n  \"prompt\": \"string\",\n  \"sessionId\": \"string\",\n  \"media\": [],\n  \"idempotencyKey\": \"string\",\n  \"credentials\": [],\n  \"framework\": \"string\",\n  \"rawConfig\": {},\n  \"timeoutSeconds\": 0\n}",
        "responseExample": "{\n  \"executionId\": \"string\",\n  \"agentName\": \"string\",\n  \"requiredWorkers\": []\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/agent/compile",
        "summary": "compileAgent",
        "description": "",
        "bodyExample": "{\n  \"agentConfig\": {\n    \"name\": \"string\",\n    \"description\": \"string\",\n    \"model\": \"string\",\n    \"instructions\": {},\n    \"tools\": [],\n    \"agents\": [],\n    \"strategy\": \"string\",\n    \"router\": {},\n    \"outputType\": {\n      \"schema\": {},\n      \"className\": \"string\"\n    },\n    \"guardrails\": [],\n    \"memory\": {\n      \"messages\": [],\n      \"maxMessages\": 0\n    },\n    \"maxTurns\": 0,\n    \"maxTokens\": 0,\n    \"timeoutSeconds\": 0,\n    \"temperature\": 0,\n    \"stopWhen\": {\n      \"taskName\": \"string\"\n    },\n    \"termination\": {\n      \"type\": \"string\",\n      \"text\": \"string\",\n      \"caseSensitive\": false,\n      \"stopMessage\": \"string\",\n      \"maxMessages\": 0,\n      \"maxTotalTokens\": 0,\n      \"maxPromptTokens\": 0,\n      \"maxCompletionTokens\": 0,\n      \"conditions\": []\n    },\n    \"handoffs\": [],\n    \"callbacks\": [],\n    \"allowedTransitions\": {},\n    \"introduction\": \"string\",\n    \"metadata\": {},\n    \"codeExecution\": {\n      \"enabled\": false,\n      \"allowedLanguages\": [],\n      \"allowedCommands\": [],\n      \"timeout\": 0\n    },\n    \"cliConfig\": {\n      \"enabled\": false,\n      \"allowedCommands\": [],\n      \"timeout\": 0,\n      \"allowShell\": false\n    },\n    \"includeContents\": \"string\",\n    \"thinkingConfig\": {\n      \"enabled\": false,\n      \"budgetTokens\": 0\n    },\n    \"planner\": false,\n    \"requiredTools\": [],\n    \"gate\": {},\n    \"credentials\": [],\n    \"external\": false\n  },\n  \"prompt\": \"string\",\n  \"sessionId\": \"string\",\n  \"media\": [],\n  \"idempotencyKey\": \"string\",\n  \"credentials\": [],\n  \"framework\": \"string\",\n  \"rawConfig\": {},\n  \"timeoutSeconds\": 0\n}",
        "responseExample": "{\n  \"workflowDef\": {},\n  \"requiredWorkers\": []\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/{name}",
        "summary": "getAgentDef",
        "description": "",
        "pathParams": [
          {
            "name": "name",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "queryParams": [
          {
            "name": "version",
            "type": "integer",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "DELETE",
        "path": "/api/agent/{name}",
        "summary": "deleteAgent",
        "description": "",
        "pathParams": [
          {
            "name": "name",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "queryParams": [
          {
            "name": "version",
            "type": "integer",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/{executionId}/status",
        "summary": "getAgentStatus",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/tasks/{taskId}/log",
        "summary": "getTaskLogs",
        "description": "",
        "pathParams": [
          {
            "name": "taskId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "[\n  {\n    \"log\": \"string\",\n    \"taskId\": \"string\",\n    \"createdTime\": 0\n  }\n]",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/stream/{executionId}",
        "summary": "streamAgent",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{\n  \"timeout\": 0\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/list",
        "summary": "listAgents",
        "description": "",
        "responseExample": "[\n  {\n    \"name\": \"string\",\n    \"version\": 0,\n    \"type\": \"string\",\n    \"tags\": [],\n    \"createTime\": 0,\n    \"updateTime\": 0,\n    \"description\": \"string\",\n    \"checksum\": \"string\"\n  }\n]",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/executions",
        "summary": "searchAgentExecutions",
        "description": "",
        "queryParams": [
          {
            "name": "start",
            "type": "integer",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "size",
            "type": "integer",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "sort",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "freeText",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "status",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "agentName",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "sessionId",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/executions/{executionId}",
        "summary": "getExecutionDetail",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{\n  \"executionId\": \"string\",\n  \"agentName\": \"string\",\n  \"version\": 0,\n  \"status\": \"string\",\n  \"input\": {},\n  \"output\": {},\n  \"currentTask\": {\n    \"taskRefName\": \"string\",\n    \"taskType\": \"string\",\n    \"status\": \"string\",\n    \"inputData\": {},\n    \"outputData\": {}\n  }\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "DELETE",
        "path": "/api/agent/executions/{executionId}",
        "summary": "terminateExecution",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "queryParams": [
          {
            "name": "reason",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/executions/{executionId}/tasks",
        "summary": "getExecutionTasks",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "queryParams": [
          {
            "name": "status",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "count",
            "type": "integer",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "start",
            "type": "integer",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "[\n  {\n    \"taskType\": \"string\",\n    \"status\": \"IN_PROGRESS\",\n    \"inputData\": {},\n    \"referenceTaskName\": \"string\",\n    \"retryCount\": 0,\n    \"seq\": 0,\n    \"correlationId\": \"string\",\n    \"pollCount\": 0,\n    \"taskDefName\": \"string\",\n    \"scheduledTime\": 0,\n    \"startTime\": 0,\n    \"endTime\": 0,\n    \"updateTime\": 0,\n    \"startDelayInSeconds\": 0,\n    \"retriedTaskId\": \"string\",\n    \"retried\": false,\n    \"executed\": false,\n    \"callbackFromWorker\": false,\n    \"responseTimeoutSeconds\": 0,\n    \"workflowInstanceId\": \"string\",\n    \"workflowType\": \"string\",\n    \"taskId\": \"string\",\n    \"reasonForIncompletion\": \"string\",\n    \"callbackAfterSeconds\": 0,\n    \"workerId\": \"string\",\n    \"outputData\": {},\n    \"workflowTask\": {\n      \"name\": \"string\",\n      \"taskReferenceName\": \"string\",\n      \"description\": \"string\",\n      \"inputParameters\": {},\n      \"type\": \"string\",\n      \"dynamicTaskNameParam\": \"string\",\n      \"caseValueParam\": \"string\",\n      \"caseExpression\": \"string\",\n      \"scriptExpression\": \"string\",\n      \"decisionCases\": {},\n      \"dynamicForkJoinTasksParam\": \"string\",\n      \"dynamicForkTasksParam\": \"string\",\n      \"dynamicForkTasksInputParamName\": \"string\",\n      \"defaultCase\": [],\n      \"forkTasks\": [],\n      \"startDelay\": 0,\n      \"subWorkflowParam\": {\n        \"name\": \"string\",\n        \"version\": 0,\n        \"taskToDomain\": {},\n        \"idempotencyKey\": \"string\",\n        \"idempotencyStrategy\": \"FAIL\",\n        \"priority\": {},\n        \"workflowDefinition\": {}\n      },\n      \"joinOn\": [],\n      \"sink\": \"string\",\n      \"optional\": false,\n      \"taskDefinition\": {\n        \"ownerApp\": \"string\",\n        \"createTime\": 0,\n        \"updateTime\": 0,\n        \"createdBy\": \"string\",\n        \"updatedBy\": \"string\",\n        \"name\": \"string\",\n        \"description\": \"string\",\n        \"retryCount\": 0,\n        \"timeoutSeconds\": 0,\n        \"inputKeys\": [],\n        \"outputKeys\": [],\n        \"timeoutPolicy\": \"RETRY\",\n        \"retryLogic\": \"FIXED\",\n        \"retryDelaySeconds\": 0,\n        \"responseTimeoutSeconds\": 0,\n        \"concurrentExecLimit\": 0,\n        \"inputTemplate\": {},\n        \"rateLimitPerFrequency\": 0,\n        \"rateLimitFrequencyInSeconds\": 0,\n        \"isolationGroupId\": \"string\",\n        \"executionNameSpace\": \"string\",\n        \"ownerEmail\": \"string\",\n        \"pollTimeoutSeconds\": 0,\n        \"backoffScaleFactor\": 0,\n        \"baseType\": \"string\",\n        \"totalTimeoutSeconds\": 0,\n        \"taskStatusListenerEnabled\": false,\n        \"inputSchema\": {},\n        \"outputSchema\": {},\n        \"enforceSchema\": false\n      },\n      \"rateLimited\": false,\n      \"defaultExclusiveJoinTask\": [],\n      \"asyncComplete\": false,\n      \"loopCondition\": \"string\",\n      \"loopOver\": [],\n      \"items\": \"string\",\n      \"retryCount\": 0,\n      \"evaluatorType\": \"string\",\n      \"expression\": \"string\",\n      \"onStateChange\": {},\n      \"joinStatus\": \"string\",\n      \"cacheConfig\": {\n        \"key\": \"string\",\n        \"ttlInSecond\": 0\n      },\n      \"permissive\": false,\n      \"joinMode\": \"SYNC\",\n      \"workflowTaskType\": \"SIMPLE\"\n    },\n    \"domain\": \"string\",\n    \"rateLimitPerFrequency\": 0,\n    \"rateLimitFrequencyInSeconds\": 0,\n    \"externalInputPayloadStoragePath\": \"string\",\n    \"externalOutputPayloadStoragePath\": \"string\",\n    \"workflowPriority\": 0,\n    \"executionNameSpace\": \"string\",\n    \"isolationGroupId\": \"string\",\n    \"iteration\": 0,\n    \"subWorkflowId\": \"string\",\n    \"subworkflowChanged\": false,\n    \"firstStartTime\": 0,\n    \"executionMetadata\": {\n      \"serverSendTime\": 0,\n      \"clientReceiveTime\": 0,\n      \"executionStartTime\": 0,\n      \"executionEndTime\": 0,\n      \"clientSendTime\": 0,\n      \"pollNetworkLatency\": 0,\n      \"updateNetworkLatency\": 0,\n      \"additionalContext\": {},\n      \"executionDuration\": 0,\n      \"additionalContextMap\": {},\n      \"empty\": false\n    },\n    \"parentTaskId\": \"string\",\n    \"taskDefinition\": {\n      \"ownerApp\": \"string\",\n      \"createTime\": 0,\n      \"updateTime\": 0,\n      \"createdBy\": \"string\",\n      \"updatedBy\": \"string\",\n      \"name\": \"string\",\n      \"description\": \"string\",\n      \"retryCount\": 0,\n      \"timeoutSeconds\": 0,\n      \"inputKeys\": [],\n      \"outputKeys\": [],\n      \"timeoutPolicy\": \"RETRY\",\n      \"retryLogic\": \"FIXED\",\n      \"retryDelaySeconds\": 0,\n      \"responseTimeoutSeconds\": 0,\n      \"concurrentExecLimit\": 0,\n      \"inputTemplate\": {},\n      \"rateLimitPerFrequency\": 0,\n      \"rateLimitFrequencyInSeconds\": 0,\n      \"isolationGroupId\": \"string\",\n      \"executionNameSpace\": \"string\",\n      \"ownerEmail\": \"string\",\n      \"pollTimeoutSeconds\": 0,\n      \"backoffScaleFactor\": 0,\n      \"baseType\": \"string\",\n      \"totalTimeoutSeconds\": 0,\n      \"taskStatusListenerEnabled\": false,\n      \"inputSchema\": {\n        \"ownerApp\": \"string\",\n        \"createTime\": 0,\n        \"updateTime\": 0,\n        \"createdBy\": \"string\",\n        \"updatedBy\": \"string\",\n        \"name\": \"string\",\n        \"version\": 0,\n        \"type\": \"JSON\",\n        \"data\": {},\n        \"externalRef\": \"string\"\n      },\n      \"outputSchema\": {\n        \"ownerApp\": \"string\",\n        \"createTime\": 0,\n        \"updateTime\": 0,\n        \"createdBy\": \"string\",\n        \"updatedBy\": \"string\",\n        \"name\": \"string\",\n        \"version\": 0,\n        \"type\": \"JSON\",\n        \"data\": {},\n        \"externalRef\": \"string\"\n      },\n      \"enforceSchema\": false\n    },\n    \"queueWaitTime\": 0,\n    \"loopOverTask\": false,\n    \"orCreateExecutionMetadata\": {\n      \"serverSendTime\": 0,\n      \"clientReceiveTime\": 0,\n      \"executionStartTime\": 0,\n      \"executionEndTime\": 0,\n      \"clientSendTime\": 0,\n      \"pollNetworkLatency\": 0,\n      \"updateNetworkLatency\": 0,\n      \"additionalContext\": {},\n      \"executionDuration\": 0,\n      \"additionalContextMap\": {},\n      \"empty\": false\n    },\n    \"executionMetadataIfHasData\": {\n      \"serverSendTime\": 0,\n      \"clientReceiveTime\": 0,\n      \"executionStartTime\": 0,\n      \"executionEndTime\": 0,\n      \"clientSendTime\": 0,\n      \"pollNetworkLatency\": 0,\n      \"updateNetworkLatency\": 0,\n      \"additionalContext\": {},\n      \"executionDuration\": 0,\n      \"additionalContextMap\": {},\n      \"empty\": false\n    }\n  }\n]",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/executions/{executionId}/full",
        "summary": "getFullExecution",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{\n  \"ownerApp\": \"string\",\n  \"createTime\": 0,\n  \"updateTime\": 0,\n  \"createdBy\": \"string\",\n  \"updatedBy\": \"string\",\n  \"status\": \"RUNNING\",\n  \"endTime\": 0,\n  \"workflowId\": \"string\",\n  \"parentWorkflowId\": \"string\",\n  \"parentWorkflowTaskId\": \"string\",\n  \"tasks\": [],\n  \"input\": {},\n  \"output\": {},\n  \"correlationId\": \"string\",\n  \"reRunFromWorkflowId\": \"string\",\n  \"reasonForIncompletion\": \"string\",\n  \"event\": \"string\",\n  \"taskToDomain\": {},\n  \"failedReferenceTaskNames\": [],\n  \"workflowDefinition\": {\n    \"ownerApp\": \"string\",\n    \"createTime\": 0,\n    \"updateTime\": 0,\n    \"createdBy\": \"string\",\n    \"updatedBy\": \"string\",\n    \"name\": \"string\",\n    \"description\": \"string\",\n    \"version\": 0,\n    \"tasks\": [],\n    \"inputParameters\": [],\n    \"outputParameters\": {},\n    \"failureWorkflow\": \"string\",\n    \"schemaVersion\": 0,\n    \"restartable\": false,\n    \"workflowStatusListenerEnabled\": false,\n    \"ownerEmail\": \"string\",\n    \"timeoutPolicy\": \"TIME_OUT_WF\",\n    \"timeoutSeconds\": 0,\n    \"variables\": {},\n    \"inputTemplate\": {},\n    \"workflowStatusListenerSink\": \"string\",\n    \"rateLimitConfig\": {\n      \"rateLimitKey\": \"string\",\n      \"concurrentExecLimit\": 0,\n      \"policy\": \"QUEUE\"\n    },\n    \"inputSchema\": {\n      \"ownerApp\": \"string\",\n      \"createTime\": 0,\n      \"updateTime\": 0,\n      \"createdBy\": \"string\",\n      \"updatedBy\": \"string\",\n      \"name\": \"string\",\n      \"version\": 0,\n      \"type\": \"JSON\",\n      \"data\": {},\n      \"externalRef\": \"string\"\n    },\n    \"outputSchema\": {\n      \"ownerApp\": \"string\",\n      \"createTime\": 0,\n      \"updateTime\": 0,\n      \"createdBy\": \"string\",\n      \"updatedBy\": \"string\",\n      \"name\": \"string\",\n      \"version\": 0,\n      \"type\": \"JSON\",\n      \"data\": {},\n      \"externalRef\": \"string\"\n    },\n    \"enforceSchema\": false,\n    \"metadata\": {},\n    \"cacheConfig\": {\n      \"key\": \"string\",\n      \"ttlInSecond\": 0\n    },\n    \"maskedFields\": []\n  },\n  \"externalInputPayloadStoragePath\": \"string\",\n  \"externalOutputPayloadStoragePath\": \"string\",\n  \"priority\": 0,\n  \"variables\": {},\n  \"lastRetriedTime\": 0,\n  \"failedTaskNames\": [],\n  \"history\": [],\n  \"idempotencyKey\": \"string\",\n  \"rateLimitKey\": \"string\",\n  \"rateLimited\": false,\n  \"workflowName\": \"string\",\n  \"workflowVersion\": 0,\n  \"startTime\": 0\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/executions/search",
        "summary": "searchExecutionsRaw",
        "description": "",
        "queryParams": [
          {
            "name": "start",
            "type": "integer",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "size",
            "type": "integer",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "sort",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "freeText",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          },
          {
            "name": "query",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{\n  \"totalHits\": 0,\n  \"results\": []\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/execution/{executionId}",
        "summary": "getExecution",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{\n  \"executionId\": \"string\",\n  \"agentName\": \"string\",\n  \"version\": 0,\n  \"status\": \"string\",\n  \"startTime\": 0,\n  \"endTime\": 0,\n  \"input\": {},\n  \"output\": {},\n  \"tokenUsage\": {\n    \"promptTokens\": 0,\n    \"completionTokens\": 0,\n    \"totalTokens\": 0\n  },\n  \"tasks\": []\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/agent/definitions/{name}",
        "summary": "getAgentDefinition",
        "description": "",
        "pathParams": [
          {
            "name": "name",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "queryParams": [
          {
            "name": "version",
            "type": "integer",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{\n  \"ownerApp\": \"string\",\n  \"createTime\": 0,\n  \"updateTime\": 0,\n  \"createdBy\": \"string\",\n  \"updatedBy\": \"string\",\n  \"name\": \"string\",\n  \"description\": \"string\",\n  \"version\": 0,\n  \"tasks\": [],\n  \"inputParameters\": [],\n  \"outputParameters\": {},\n  \"failureWorkflow\": \"string\",\n  \"schemaVersion\": 0,\n  \"restartable\": false,\n  \"workflowStatusListenerEnabled\": false,\n  \"ownerEmail\": \"string\",\n  \"timeoutPolicy\": \"TIME_OUT_WF\",\n  \"timeoutSeconds\": 0,\n  \"variables\": {},\n  \"inputTemplate\": {},\n  \"workflowStatusListenerSink\": \"string\",\n  \"rateLimitConfig\": {\n    \"rateLimitKey\": \"string\",\n    \"concurrentExecLimit\": 0,\n    \"policy\": \"QUEUE\"\n  },\n  \"inputSchema\": {\n    \"ownerApp\": \"string\",\n    \"createTime\": 0,\n    \"updateTime\": 0,\n    \"createdBy\": \"string\",\n    \"updatedBy\": \"string\",\n    \"name\": \"string\",\n    \"version\": 0,\n    \"type\": \"JSON\",\n    \"data\": {},\n    \"externalRef\": \"string\"\n  },\n  \"outputSchema\": {\n    \"ownerApp\": \"string\",\n    \"createTime\": 0,\n    \"updateTime\": 0,\n    \"createdBy\": \"string\",\n    \"updatedBy\": \"string\",\n    \"name\": \"string\",\n    \"version\": 0,\n    \"type\": \"JSON\",\n    \"data\": {},\n    \"externalRef\": \"string\"\n  },\n  \"enforceSchema\": false,\n  \"metadata\": {},\n  \"cacheConfig\": {\n    \"key\": \"string\",\n    \"ttlInSecond\": 0\n  },\n  \"maskedFields\": []\n}",
        "tags": [
          "agent-controller"
        ]
      },
      {
        "method": "DELETE",
        "path": "/api/agent/{executionId}/cancel",
        "summary": "cancelAgent",
        "description": "",
        "pathParams": [
          {
            "name": "executionId",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "queryParams": [
          {
            "name": "reason",
            "type": "string",
            "required": false,
            "description": "",
            "example": ""
          }
        ],
        "tags": [
          "agent-controller"
        ]
      }
    ]
  },
  {
    "name": "Credential",
    "description": "Credential endpoints",
    "endpoints": [
      {
        "method": "GET",
        "path": "/api/credentials/{name}",
        "summary": "getCredential",
        "description": "",
        "pathParams": [
          {
            "name": "name",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{}",
        "tags": [
          "credential-controller"
        ]
      },
      {
        "method": "PUT",
        "path": "/api/credentials/{name}",
        "summary": "updateCredential",
        "description": "",
        "pathParams": [
          {
            "name": "name",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "bodyExample": "{}",
        "responseExample": "{}",
        "tags": [
          "credential-controller"
        ]
      },
      {
        "method": "DELETE",
        "path": "/api/credentials/{name}",
        "summary": "deleteCredential",
        "description": "",
        "pathParams": [
          {
            "name": "name",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{}",
        "tags": [
          "credential-controller"
        ]
      },
      {
        "method": "PUT",
        "path": "/api/credentials/bindings/{key}",
        "summary": "setBinding",
        "description": "",
        "pathParams": [
          {
            "name": "key",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "bodyExample": "{}",
        "responseExample": "{}",
        "tags": [
          "credential-controller"
        ]
      },
      {
        "method": "DELETE",
        "path": "/api/credentials/bindings/{key}",
        "summary": "deleteBinding",
        "description": "",
        "pathParams": [
          {
            "name": "key",
            "type": "string",
            "required": true,
            "description": "",
            "example": ""
          }
        ],
        "responseExample": "{}",
        "tags": [
          "credential-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/credentials",
        "summary": "listCredentials",
        "description": "",
        "responseExample": "{}",
        "tags": [
          "credential-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/credentials",
        "summary": "createCredential",
        "description": "",
        "bodyExample": "{}",
        "responseExample": "{}",
        "tags": [
          "credential-controller"
        ]
      },
      {
        "method": "POST",
        "path": "/api/credentials/resolve",
        "summary": "resolve",
        "description": "",
        "bodyExample": "{\n  \"token\": \"string\",\n  \"names\": []\n}",
        "responseExample": "{}",
        "tags": [
          "credential-controller"
        ]
      },
      {
        "method": "GET",
        "path": "/api/credentials/bindings",
        "summary": "listBindings",
        "description": "",
        "responseExample": "{}",
        "tags": [
          "credential-controller"
        ]
      }
    ]
  }
] as const;
