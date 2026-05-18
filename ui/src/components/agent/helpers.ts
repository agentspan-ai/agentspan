export const testWorkflowDefOrExecutionViewPathname = (pathname: string) => {
  return (
    /^\/agentDef\/.*$/.test(pathname) ||
    /^\/execution\/.*$/.test(pathname) ||
    pathname.startsWith("/newWorkflowDef")
  );
};
