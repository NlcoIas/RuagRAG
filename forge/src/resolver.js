import Resolver from "@forge/resolver";
import api, { route, storage, fetch } from "@forge/api";

const resolver = new Resolver();

/**
 * Extract plain text from an Atlassian Document Format (ADF) node.
 */
function adfToText(adf) {
  if (!adf || !adf.content) return "";
  let text = "";
  for (const block of adf.content) {
    if (block.type === "paragraph" && block.content) {
      for (const inline of block.content) {
        if (inline.type === "text") {
          text += inline.text || "";
        }
      }
      text += "\n";
    } else if (block.type === "text") {
      text += block.text || "";
    } else if (block.content) {
      text += adfToText(block);
    }
  }
  return text.trim();
}

/**
 * Read the value of a select custom field (returns the option's name string).
 */
function selectValue(field) {
  if (!field) return "";
  if (typeof field === "string") return field;
  return field.value || field.name || "";
}

/**
 * Load initial data for the panel: AI suggestion + metadata + version history.
 */
resolver.define("getInitialData", async ({ payload, context }) => {
  const issueKey = context.extension.issue.key;

  // Fetch issue fields
  const resp = await api.asApp().requestJira(
    route`/rest/api/3/issue/${issueKey}?fields=customfield_10055,customfield_10056,customfield_10057,customfield_10058,customfield_10059,customfield_10062`
  );
  const issue = await resp.json();
  const fields = issue.fields || {};

  // Extract suggestion text from ADF
  const suggestionAdf = fields.customfield_10062;
  const suggestionText = suggestionAdf ? adfToText(suggestionAdf) : "";

  // Extract metadata
  const metadata = {
    confidence: selectValue(fields.customfield_10055),
    department: selectValue(fields.customfield_10056),
    triageLevel: selectValue(fields.customfield_10057),
    kbScore: fields.customfield_10058 || 0,
    ticketScore: fields.customfield_10059 || 0,
  };

  // Load version history from Forge Storage
  const storageKey = `versions-${issueKey}`;
  const stored = await storage.get(storageKey);
  let versions = stored || [];

  // If no versions yet, initialize with the original suggestion
  if (versions.length === 0 && suggestionText) {
    versions = [{ text: suggestionText, feedback: null, timestamp: Date.now() }];
    await storage.set(storageKey, versions);
  }

  return { issueKey, suggestion: suggestionText, metadata, versions };
});

/**
 * Refine the suggestion text via the FastAPI /api/refine endpoint.
 */
resolver.define("refine", async ({ payload, context }) => {
  const { currentText, feedback } = payload;
  const issueKey = context.extension.issue.key;

  const apiUrl = process.env.RUAGRAG_API_URL;
  const apiKey = process.env.FORGE_API_KEY;

  const headers = { "Content-Type": "application/json" };
  if (apiKey) {
    headers["Authorization"] = `Bearer ${apiKey}`;
  }

  const resp = await fetch(`${apiUrl}/api/refine`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      current_text: currentText,
      feedback: feedback,
      issue_key: issueKey,
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    return { refined_text: currentText, success: false, error: errText };
  }

  const data = await resp.json();

  if (data.success) {
    // Save new version to Forge Storage
    const storageKey = `versions-${issueKey}`;
    const stored = (await storage.get(storageKey)) || [];
    stored.push({
      text: data.refined_text,
      feedback: feedback,
      timestamp: Date.now(),
    });
    await storage.set(storageKey, stored);
  }

  return data;
});

/**
 * Send the final text as a public customer comment on the Jira issue.
 */
resolver.define("send", async ({ payload, context }) => {
  const { text } = payload;
  const issueKey = context.extension.issue.key;

  const adfBody = {
    version: 1,
    type: "doc",
    content: [
      {
        type: "paragraph",
        content: [{ type: "text", text: text }],
      },
    ],
  };

  const resp = await api.asApp().requestJira(
    route`/rest/api/3/issue/${issueKey}/comment`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ body: adfBody }),
    }
  );

  if (resp.ok) {
    return { success: true };
  }

  const errText = await resp.text();
  return { success: false, error: errText };
});

export const handler = resolver.getDefinitions();
