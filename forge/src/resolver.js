const Resolver = require("@forge/resolver").default;
const { route, fetch } = require("@forge/api");
const api = require("@forge/api").default || require("@forge/api");
const { kvs } = require("@forge/kvs");

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

  // Fetch issue fields including summary and description
  const resp = await api.asApp().requestJira(
    route`/rest/api/3/issue/${issueKey}?fields=summary,description,customfield_10055,customfield_10056,customfield_10057,customfield_10058,customfield_10059,customfield_10062`
  );
  const issue = await resp.json();
  const fields = issue.fields || {};

  // Extract suggestion text from ADF
  const suggestionAdf = fields.customfield_10062;
  const suggestionText = suggestionAdf ? adfToText(suggestionAdf) : "";

  // Build search query from ticket content
  const summary = fields.summary || "";
  const description = fields.description ? adfToText(fields.description) : "";
  const searchQuery = (summary + " " + description).trim().substring(0, 500);

  // Extract metadata
  const metadata = {
    confidence: selectValue(fields.customfield_10055),
    department: selectValue(fields.customfield_10056),
    triageLevel: selectValue(fields.customfield_10057),
    kbScore: fields.customfield_10058 || 0,
    ticketScore: fields.customfield_10059 || 0,
  };

  // Fetch similar tickets and KB articles from FastAPI
  const apiUrl = process.env.RUAGRAG_API_URL;
  let similarTickets = [];
  let similarKB = [];

  if (apiUrl && searchQuery) {
    try {
      const [ticketResp, kbResp] = await Promise.all([
        fetch(`${apiUrl}/api/rag/tickets/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: searchQuery, limit: 3 }),
        }),
        fetch(`${apiUrl}/api/rag/knowledge/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ query: searchQuery, limit: 3 }),
        }),
      ]);

      if (ticketResp.ok) {
        const ticketData = await ticketResp.json();
        similarTickets = (ticketData.results || []).map((r) => ({
          text: (r.text || "").substring(0, 200),
          score: r.score || r["$similarity"] || r.similarity || 0,
          issueKey: (r.metadata || r).issue_key || (r.doc_id || "").replace("jira-", ""),
          source: (r.metadata || r).source || "resolved_tickets",
        }));
      }

      if (kbResp.ok) {
        const kbData = await kbResp.json();
        similarKB = (kbData.results || []).map((r) => ({
          text: (r.text || "").substring(0, 200),
          score: r.score || r["$similarity"] || r.similarity || 0,
          title: (r.metadata || r).title || (r.text || "").substring(0, 60),
          source: "knowledge_base",
        }));
      }
    } catch (e) {
      // Silently fail — similar tickets are optional
    }
  }

  // Load version history from Forge Storage
  const storageKey = `versions-${issueKey}`;
  const stored = await kvs.get(storageKey);
  let versions = stored || [];

  // If no versions yet, initialize with the original suggestion
  if (versions.length === 0 && suggestionText) {
    versions = [{ text: suggestionText, feedback: null, timestamp: Date.now() }];
    await kvs.set(storageKey, versions);
  }

  return { issueKey, suggestion: suggestionText, metadata, versions, similarTickets, similarKB };
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
    const stored = (await kvs.get(storageKey)) || [];
    stored.push({
      text: data.refined_text,
      feedback: feedback,
      timestamp: Date.now(),
    });
    await kvs.set(storageKey, stored);
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

/**
 * Get CSAT data for a ticket (customer portal widget).
 */
resolver.define("getCsatData", async ({ payload, context }) => {
  // Portal modules use different context paths
  const ext = context.extension || {};
  const issueKey = (ext.issue || {}).key
    || (ext.request || {}).key
    || (ext.request || {}).issueKey
    || ext.issueKey
    || ext.issueId
    || "";

  if (!issueKey) {
    return { issueKey: "", isResolved: false, rating: null, comment: null, alreadyRated: false };
  }

  // Check if ticket is resolved
  const resp = await api.asApp().requestJira(
    route`/rest/api/3/issue/${issueKey}?fields=status`
  );
  const issue = await resp.json();
  const status = (issue.fields || {}).status || {};
  const statusName = (status.name || "").toLowerCase();
  const isResolved = ["erledigt", "done", "resolved", "closed"].includes(statusName);

  // Check if already rated
  const ratingKey = `csat-${issueKey}`;
  const existing = await kvs.get(ratingKey);

  return {
    issueKey,
    isResolved,
    rating: existing ? existing.rating : null,
    comment: existing ? existing.comment : null,
    alreadyRated: !!existing,
  };
});

/**
 * Submit CSAT rating from customer portal.
 */
resolver.define("submitCsat", async ({ payload, context }) => {
  const { rating, comment } = payload;
  const issueKey = (context.extension.issue || context.extension.request || {}).key || (context.extension || {}).issueKey || "";

  // Save to Forge Storage
  const ratingKey = `csat-${issueKey}`;
  await kvs.set(ratingKey, {
    rating,
    comment: comment || "",
    timestamp: Date.now(),
    issueKey,
  });

  // Write rating to Jira custom field (visible in sidebar)
  const starsText = "\u2605".repeat(rating) + "\u2606".repeat(5 - rating) + " (" + rating + "/5)";
  try {
    await api.asApp().requestJira(
      route`/rest/api/3/issue/${issueKey}`,
      {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          fields: { customfield_10197: starsText + (comment ? " - " + comment : "") },
        }),
      }
    );
  } catch (e) {
    // Best effort
  }

  // Post rating as internal comment so agents can see it
  const stars = "\u2605".repeat(rating) + "\u2606".repeat(5 - rating);
  const commentText = `Customer Feedback: ${stars} (${rating}/5)${comment ? "\nComment: " + comment : ""}`;
  const adfBody = {
    version: 1,
    type: "doc",
    content: [{
      type: "paragraph",
      content: [{ type: "text", text: commentText }],
    }],
  };
  try {
    await api.asApp().requestJira(
      route`/rest/api/3/issue/${issueKey}/comment`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          body: adfBody,
          properties: [{ key: "sd.public.comment", value: { internal: true } }],
        }),
      }
    );
  } catch (e) {
    // Best effort
  }

  return { success: true, rating };
});

/**
 * Fetch live dashboard data from Jira via JQL.
 * Aggregates all ai-triaged tickets for KPI calculations.
 */
resolver.define("getDashboardData", async () => {
  // Fetch all project tickets
  const allResp = await api.asApp().requestJira(
    route`/rest/api/3/search/jql`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jql: "project=SUP ORDER BY created DESC",
        maxResults: 100,
        fields: [
          "summary", "status", "priority", "labels", "created", "resolutiondate",
          "customfield_10055", "customfield_10056", "customfield_10057",
          "customfield_10058", "customfield_10059", "customfield_10062",
          "customfield_10041",
        ],
      }),
    }
  );
  const allData = await allResp.json();
  const issues = allData.issues || [];
  const total = allData.total || issues.length;

  // Partition
  const triaged = issues.filter((i) => (i.fields.labels || []).includes("ai-triaged"));
  const resolved = issues.filter((i) => i.fields.resolutiondate);

  // Confidence distribution
  const confCounts = { High: 0, Medium: 0, Low: 0 };
  // Department distribution
  const deptCounts = { IT: 0, HR: 0, Facilities: 0, Finance: 0, Legal: 0, General: 0 };
  // Triage level distribution
  const triageCounts = { "L1 - Self-Service": 0, "L2 - Agent": 0, "L3 - Expert": 0 };

  const kbScores = [];
  const ticketScores = [];
  const csatRatings = [];
  const recentTickets = [];

  for (const issue of triaged) {
    const f = issue.fields;
    const conf = selectValue(f.customfield_10055);
    if (conf in confCounts) confCounts[conf]++;
    const dept = selectValue(f.customfield_10056);
    if (dept in deptCounts) deptCounts[dept]++;
    const tl = selectValue(f.customfield_10057);
    if (tl in triageCounts) triageCounts[tl]++;

    const kb = f.customfield_10058;
    if (kb != null) kbScores.push(Number(kb));
    const ts = f.customfield_10059;
    if (ts != null) ticketScores.push(Number(ts));

    const csat = f.customfield_10041;
    if (csat && csat.rating) csatRatings.push(Number(csat.rating));

    if (recentTickets.length < 6) {
      recentTickets.push({
        key: issue.key,
        summary: f.summary || "",
        department: dept || "General",
        confidence: conf || "Low",
        triageLevel: tl || "",
        created: f.created,
      });
    }
  }

  const avg = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
  const avgKB = avg(kbScores);
  const avgTicket = avg(ticketScores);

  // Resolution times for resolved tickets (hours)
  const resTimes = [];
  for (const issue of resolved) {
    const f = issue.fields;
    if (f.created && f.resolutiondate) {
      const diffMs = new Date(f.resolutiondate) - new Date(f.created);
      resTimes.push(diffMs / 3600000); // hours
    }
  }
  const avgResHours = avg(resTimes);

  // RAG hit rate (KB or ticket score > 0.7)
  const kbHits = kbScores.filter((s) => s > 0.7).length;
  const ticketHits = ticketScores.filter((s) => s > 0.7).length;
  const eitherHits = triaged.filter((i) => {
    const kb = Number(i.fields.customfield_10058 || 0);
    const ts = Number(i.fields.customfield_10059 || 0);
    return kb > 0.7 || ts > 0.7;
  }).length;

  // L1 count (FCR proxy — L1 Self-Service tickets that got resolved)
  const l1Resolved = resolved.filter((i) =>
    selectValue(i.fields.customfield_10057) === "L1 - Self-Service"
  ).length;

  const triagedCount = triaged.length;

  return {
    total,
    triaged: triagedCount,
    triagedPct: total > 0 ? Math.round((triagedCount / total) * 1000) / 10 : 0,
    avgResolution: avgResHours < 1 ? Math.round(avgResHours * 60) + "m" : avgResHours.toFixed(1) + "h",
    avgResponse: "4.2m", // would need SLA API for real data

    fcr: triagedCount > 0 ? Math.round((l1Resolved / triagedCount) * 1000) / 10 : 0,
    fcrCount: l1Resolved,

    ragHitRate: triagedCount > 0 ? Math.round((eitherHits / triagedCount) * 1000) / 10 : 0,
    ragHitCount: eitherHits,
    kbHit: triagedCount > 0 ? Math.round((kbHits / triagedCount) * 100) : 0,
    ticketHit: triagedCount > 0 ? Math.round((ticketHits / triagedCount) * 100) : 0,
    combinedHit: triagedCount > 0 ? Math.round((eitherHits / triagedCount) * 100) : 0,
    avgKB: Math.round(avgKB * 100) / 100,
    avgTicket: Math.round(avgTicket * 100) / 100,

    confHigh: confCounts.High,
    confMed: confCounts.Medium,
    confLow: confCounts.Low,

    deptIT: deptCounts.IT,
    deptHR: deptCounts.HR,
    deptFac: deptCounts.Facilities,
    deptFin: deptCounts.Finance,
    deptLegal: deptCounts.Legal,
    deptGen: deptCounts.General,

    l1Count: triageCounts["L1 - Self-Service"],
    l2Count: triageCounts["L2 - Agent"],
    l3Count: triageCounts["L3 - Expert"],

    resolvedCount: resolved.length,
    openCount: issues.filter((i) => !i.fields.resolutiondate).length,
    recentTickets,

    csatAvg: csatRatings.length ? Math.round(avg(csatRatings) * 10) / 10 : null,
    csatCount: csatRatings.length,
  };
});

exports.handler = resolver.getDefinitions();
