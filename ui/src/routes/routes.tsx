/**
 * Routes Configuration
 *
 * This module defines the application routes. Core routes are defined inline,
 * while enterprise routes are registered via the plugin system.
 *
 * Core routes (OSS):
 * - Agent definitions and executions
 * - Scheduler definitions and executions
 * - Queue monitor
 * - API reference
 * - Credentials management
 *
 * Enterprise routes (registered via plugins):
 * - Auth (login, callbacks, RBAC pages)
 * - Webhooks
 * - Human Tasks
 * - AI Prompts
 * - Secrets
 * - Integrations
 * - Gateway Services
 * - Remote Services
 * - Metrics
 * - Environment Variables
 * - Schemas
 * - Workers
 */

import { App } from "components/App";
import DefaultAuthGuard from "components/auth/AuthGuard";
import ApiReferencePage from "pages/apiDocs/ApiReferencePage";
import { CredentialsPage } from "pages/credentials";
import WorkflowDefinition from "pages/definition/WorkflowDefinition";
import {
  Schedules as ScheduleDefinitions,
  Agent as AgentDefinitions,
} from "pages/definitions";
import ErrorPage from "pages/error/ErrorPage";
import { SchedulerExecutions, AgentSearch } from "pages/executions";
import { pluginRegistry } from "plugins/registry";
import { featureFlags, FEATURES } from "utils";
import {
  API_REFERENCE_URL,
  CREDENTIALS_URL,
  RUN_AGENT_URL,
  SCHEDULER_DEFINITION_URL,
  TASK_QUEUE_URL,
  AGENT_DEFINITION_URL,
} from "utils/constants/route";
import Execution from "../pages/execution/Execution";
import TaskQueue from "../pages/queueMonitor/TaskQueue";
import { Schedule } from "../pages/scheduler";

/**
 * Core authenticated routes (OSS)
 * These are the fundamental Conductor UI features available in open source.
 */
const getCoreAuthenticatedRoutes = () => [
  // Agent Executions
  {
    path: "/executions",
    element: <AgentSearch />,
  },
  {
    path: "/schedulerExecs",
    element: <SchedulerExecutions />,
  },
  {
    path: "/execution/:id/:taskId?",
    element: <Execution />,
  },

  // Agent Definitions
  {
    path: AGENT_DEFINITION_URL.BASE,
    element: <AgentDefinitions />,
  },
  {
    path: AGENT_DEFINITION_URL.NAME_VERSION,
    element: <WorkflowDefinition />,
  },

  // Credentials
  {
    path: CREDENTIALS_URL,
    element: <CredentialsPage />,
  },

  // Scheduler Definitions
  {
    path: SCHEDULER_DEFINITION_URL.BASE,
    element: <ScheduleDefinitions />,
  },
  {
    path: SCHEDULER_DEFINITION_URL.NAME,
    element: <Schedule />,
  },
  {
    path: SCHEDULER_DEFINITION_URL.NEW,
    element: <Schedule />,
  },

  // Queue Monitor
  {
    path: TASK_QUEUE_URL.BASE,
    element: <TaskQueue />,
  },

  // API Reference
  {
    path: API_REFERENCE_URL.BASE,
    element: <ApiReferencePage />,
  },

];

/**
 * Get the default index route based on feature flags
 */
const getIndexRoute = (isPlayground: boolean) => {
  if (isPlayground) {
    // In playground mode, we need the hub pages - these come from plugins
    return null; // Will be provided by playground plugin
  }
  return {
    index: true,
    element: <AgentSearch />,
  };
};

/**
 * Build the complete route configuration
 */
export const getRoutes = () => {
  const isPlayground = featureFlags.isEnabled(FEATURES.PLAYGROUND);

  // Get routes from plugins
  const pluginAuthenticatedRoutes = pluginRegistry.getRoutes();
  const pluginPublicRoutes = pluginRegistry.getPublicRoutes();

  // Get auth guard from plugins (enterprise) or use default (OSS)
  const AuthGuard = pluginRegistry.getAuthGuard() || DefaultAuthGuard;

  // Core authenticated routes
  const coreRoutes = getCoreAuthenticatedRoutes();

  // Build the index route (either core AgentSearch or from playground plugin)
  const indexRoute = getIndexRoute(isPlayground);

  // Combine all authenticated routes
  const allAuthenticatedRoutes = [
    ...(indexRoute ? [indexRoute] : []),
    ...coreRoutes,
    ...pluginAuthenticatedRoutes,
  ];

  return [
    {
      path: "/",
      element: <App />,
      children: [
        // Main authenticated section
        {
          element: <AuthGuard />,
          children: allAuthenticatedRoutes,
        },

        // Special route for runWorkflow (has special AuthGuard behavior)
        {
          path: RUN_AGENT_URL,
          element: <AuthGuard runWorkflow={true} />,
        },

        // Public routes from plugins (login pages, OAuth callbacks, etc.)
        ...pluginPublicRoutes,

        // Error page (catch-all)
        {
          path: "*",
          element: <ErrorPage />,
        },
      ],
    },
  ];
};
