/**
 * Core (OSS) sidebar menu items for Conductor UI.
 *
 * These items are merged with plugin-registered items in UiSidebar.
 * - Executions submenu (Agent, Queue Monitor)
 * - Run Agent button
 * - Definitions submenu (Agent, Task, Event Handler)
 * - Help menu
 * - API Docs
 */

import CodeIcon from "@mui/icons-material/Code";
import MenuBookOutlinedIcon from "@mui/icons-material/MenuBookOutlined";
import PlayIcon from "@mui/icons-material/PlayArrowOutlined";
import PlaylistPlayIcon from "@mui/icons-material/PlaylistPlay";
import WebhookOutlinedIcon from "@mui/icons-material/WebhookOutlined";
import RunAgentButton from "components/Sidebar/RunAgentButton";
import DiscordIcon from "components/Sidebar/DiscordIcon";
import { MenuItemType } from "components/Sidebar/types";

import {
  CREDENTIALS_URL,
  RUN_AGENT_URL,
  TASK_QUEUE_URL,
  AGENT_DEFINITION_URL,
  AGENT_EXECUTION_URL,
} from "utils/constants/route";

/**
 * Core sidebar position constants. Root and submenus both use 100, 200, 300, ...
 * so plugins can inject items in between (e.g. position 150 between 100 and 200).
 * Export for orkes-conductor-ui to reference when registering sidebar items.
 */
const CORE_SIDEBAR_POSITIONS = {
  // Root level (top-level menu items)
  ROOT: {
    executionsSubMenu: 100,
    runWorkflow: 200,
    definitionsSubMenu: 300,
    swaggerItem: 500,
    docsItem: 600,
    discordItem: 700,
  },
  // Executions submenu children
  EXECUTIONS: {
    workflowExeItem: 100,
    queueMonitorItem: 200,
  },
  // Definitions submenu children
  DEFINITIONS: {
    workflowDefItem: 100,
    credentialsItem: 200,
  },
} as const;

/**
 * Returns the core OSS sidebar menu items. Accepts `open` for the Run Workflow
 * button component which depends on sidebar open state.
 * Each item has a numeric position so plugins can inject between (e.g. 150 between 100 and 200).
 */
export function getCoreSidebarItems(open: boolean): MenuItemType[] {
  const R = CORE_SIDEBAR_POSITIONS.ROOT;
  const E = CORE_SIDEBAR_POSITIONS.EXECUTIONS;
  const D = CORE_SIDEBAR_POSITIONS.DEFINITIONS;

  return [
    // Executions submenu - core items only
    {
      id: "executionsSubMenu",
      title: "Executions",
      icon: <PlaylistPlayIcon />,
      linkTo: "",
      shortcuts: [],
      hotkeys: "",
      hidden: false,
      position: R.executionsSubMenu,
      items: [
        {
          id: "workflowExeItem",
          title: "Agents",
          icon: null,
          linkTo: "/executions",
          activeRoutes: [AGENT_EXECUTION_URL.WF_ID_TASK_ID],
          shortcuts: [],
          hotkeys: "",
          hidden: false,
          position: E.workflowExeItem,
        },
        {
          id: "queueMonitorItem",
          title: "Queue Monitor",
          icon: null,
          linkTo: TASK_QUEUE_URL.BASE,
          shortcuts: [],
          hotkeys: "",
          hidden: false,
          position: E.queueMonitorItem,
        },
      ],
    },
    // Run Workflow button
    {
      id: "runWorkflow",
      title: "Run Agent",
      icon: <PlayIcon />,
      linkTo: RUN_AGENT_URL,
      shortcuts: [],
      hidden: true,
      position: R.runWorkflow,
      component: <RunAgentButton open={open} />,
    },
    // Definitions submenu - core items only
    {
      id: "definitionsSubMenu",
      title: "Definitions",
      icon: <CodeIcon />,
      linkTo: "",
      shortcuts: [],
      hotkeys: "",
      hidden: false,
      position: R.definitionsSubMenu,
      items: [
        {
          id: "workflowDefItem",
          title: "Agent",
          icon: null,
          linkTo: AGENT_DEFINITION_URL.BASE,
          activeRoutes: [
            AGENT_DEFINITION_URL.NAME_VERSION,
          ],
          shortcuts: [],
          hotkeys: "",
          hidden: false,
          position: D.workflowDefItem,
        },
        {
          id: "credentialsItem",
          title: "Credentials",
          icon: null,
          linkTo: CREDENTIALS_URL,
          activeRoutes: [CREDENTIALS_URL],
          shortcuts: [],
          hotkeys: "",
          hidden: false,
          position: D.credentialsItem,
        },
      ],
    },
    // API Docs
    {
      id: "swaggerItem",
      title: "API Docs",
      icon: <WebhookOutlinedIcon />,
      linkTo: "/docs",
      shortcuts: [],
      hotkeys: "",
      hidden: false,
      position: R.swaggerItem,
    },
    // Docs
    {
      id: "docsItem",
      title: "Docs",
      icon: <MenuBookOutlinedIcon />,
      linkTo: "https://agentspan.ai/docs",
      shortcuts: [],
      hotkeys: "",
      hidden: false,
      position: R.docsItem,
      isOpenNewTab: true,
    },
    // Discord
    {
      id: "discordItem",
      title: "Discord",
      icon: <DiscordIcon />,
      linkTo: "https://discord.com/invite/ajcA66JcKq",
      shortcuts: [],
      hotkeys: "",
      hidden: false,
      position: R.discordItem,
      isOpenNewTab: true,
    },
  ];
}
