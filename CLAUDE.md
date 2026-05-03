1. When adding e2e make sure not to use LLM for validation unless we are doing this for judging quality/output/evals
2. Write a test, then validate that the test is actually valid. make it fail, assert that it did fail so we know its corect
3. E2E tests MUST NOT run longer than 12 minutes total. If a full e2e suite takes longer, split it or run subsets. Individual test timeouts should be set accordingly.
