import Resolver from "@forge/resolver";

const resolver = new Resolver();

resolver.define("getInitialData", async ({ payload, context }) => {
  return { suggestion: "", metadata: {}, versions: [] };
});

resolver.define("refine", async ({ payload }) => {
  return { refined_text: "", success: false };
});

resolver.define("send", async ({ payload }) => {
  return { success: false };
});

export const handler = resolver.getDefinitions();
