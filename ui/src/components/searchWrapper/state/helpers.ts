/**
 * Search helpers for the core OSS search machine.
 *
 * This file handles fuzzy search and result formatting for the core OSS
 * searchable categories: agents and schedulers.
 *
 * Enterprise categories (users, groups, applications, webhooks, integrations,
 * prompts, user forms) are handled by enterprise plugins via searchProviders.
 */

import { MenuItemType } from "components/Sidebar/types";
import fastDeepEqual from "fast-deep-equal";
import Fuse from "fuse.js";
import { CommonDef } from "./types";
import { getUniqueWorkflows } from "utils/workflow";
import { WorkflowDef } from "types/WorkflowDef";
import _isEmpty from "lodash/isEmpty";
import _identity from "lodash/identity";
import _prop from "lodash/fp/prop";
import {
  SCHEDULER_DEFINITION_URL,
  AGENT_DEFINITION_URL,
} from "utils/constants/route";

export interface SearchResultExtractorProps {
  workflowDefinitions?: WorkflowDef[];
  scheduler?: string[];
  searchTerm: string;
  maxSearchResults?: number;
}

export const searchFunction = (
  targets: CommonDef[] | string[],
  searchTerm: string,
  maxSearchResults?: number,
  keys?: string[],
) => {
  const fuseInstance = new Fuse<string | CommonDef>(targets, {
    includeScore: false,
    threshold: 0.2, // https://www.fusejs.io/api/options.html#threshold
    ...(keys && { keys: keys }),
  });
  const searchResults = fuseInstance.search(searchTerm ?? "");
  const limitedSearchResults = () => {
    if (maxSearchResults) {
      return searchResults && searchResults.length > maxSearchResults
        ? searchResults.slice(0, maxSearchResults)
        : searchResults;
    }
    return searchResults;
  };
  return limitedSearchResults().map(({ item }) => item);
};

const fromName = _prop("name");

const allWhenSearchTerm =
  (searchTerm: string) =>
  (
    items: Array<CommonDef | string> = [],
    config: {
      routePrefix: string;
      viewAllTitle: string;
      toSuffix?: (a: string | CommonDef) => string;
      toLabel?: (a: string | CommonDef) => string;
    },
  ) => {
    const {
      routePrefix,
      viewAllTitle,
      toSuffix = _identity,
      toLabel = _identity,
    } = config;
    if (!_isEmpty(searchTerm)) {
      return [
        { route: routePrefix, title: viewAllTitle },
        ...items.map((item) => {
          return {
            route: `${routePrefix}/${toSuffix(item)}`,
            title: toLabel(item) as string,
          };
        }),
      ];
    }

    return [];
  };

export const searchResultExtractor = ({
  workflowDefinitions,
  scheduler,
  searchTerm,
  maxSearchResults,
}: SearchResultExtractorProps) => {
  let wfSearchResult;
  let schedulerSearchResult;

  if (workflowDefinitions && workflowDefinitions.length > 0) {
    wfSearchResult = searchFunction(
      getUniqueWorkflows(workflowDefinitions),
      searchTerm,
      maxSearchResults,
      ["name", "description"],
    );
  }

  if (scheduler && scheduler.length > 0) {
    schedulerSearchResult = searchFunction(
      scheduler,
      searchTerm,
      maxSearchResults,
    );
  }

  const searchResultsToRoutes = allWhenSearchTerm(searchTerm);

  const workflowDefinitionsSub = searchResultsToRoutes(wfSearchResult, {
    routePrefix: AGENT_DEFINITION_URL.BASE,
    viewAllTitle: "View all agent definitions",
    toSuffix: fromName,
    toLabel: fromName,
  });

  const schedulerSub = searchResultsToRoutes(schedulerSearchResult, {
    routePrefix: SCHEDULER_DEFINITION_URL.BASE,
    viewAllTitle: "View all schedulers",
  });

  const emptyOutput = [
    { title: "Agents", sub: [], route: AGENT_DEFINITION_URL.BASE },
    { title: "Schedules", sub: [], route: SCHEDULER_DEFINITION_URL.BASE },
  ];

  const dataOutput = [
    {
      title: "Agents",
      route: AGENT_DEFINITION_URL.BASE,
      sub: workflowDefinitionsSub ?? [],
    },
    {
      title: "Schedules",
      route: SCHEDULER_DEFINITION_URL.BASE,
      sub: schedulerSub ?? [],
    },
  ].sort(({ sub: subA }, { sub: subB }) => subB.length - subA.length);

  if (searchTerm === "") {
    return null;
  }

  if (fastDeepEqual(emptyOutput, dataOutput)) {
    return [];
  }

  return dataOutput;
};

export const flattenMenu = (
  menuItems: MenuItemType[],
  parentTitle?: string,
) => {
  const result: { route: string; title: string }[] = [];

  menuItems.forEach(({ title, items, linkTo, hidden }) => {
    if (!hidden) {
      if (items && items.length > 0) {
        result.push(...flattenMenu(items, title));

        return;
      }

      const tempTitle = parentTitle ? `${parentTitle} - ${title}` : title;

      if (linkTo) {
        result.push({ route: linkTo, title: tempTitle });

        return;
      }
    }
  });

  return result;
};
