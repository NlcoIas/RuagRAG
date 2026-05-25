# Dashboard Redesign — 5-Category KPI Structure

## Goal

Restructure the Forge AI Support Dashboard so a manager can glance at 5 top-level aggregate cards and instantly know which areas are healthy and which need attention, then drill into sub-KPIs per category.

## Files to Change

- `forge/frontend/src/Dashboard.jsx` — complete rewrite of layout and sections
- `forge/src/resolver.js` — add `openCount` to `getDashboardData` return value

No backend (`app/`) changes needed.

## Layout

```
Header (RUAG red bar, title, ticket count)
LIVE/DEMO legend
─────────────────────────────────────────
5 Aggregate Cards (1 row, equal width)
  [Efficiency] [Quality] [Cust. Exp] [Support Int.] [Technical]
─────────────────────────────────────────
Section: EFFICIENCY (4 sub-KPI cards)
Section: QUALITY (2 sub-KPI cards)
Section: CUSTOMER EXPERIENCE (2 sub-KPI cards)
Section: SUPPORT INTENSITY (1 sub-KPI card, full width)
Section: TECHNICAL (4 sub-KPI cards)
─────────────────────────────────────────
Section: ANALYTICS (existing charts, 2-col grid)
  - Tickets by Department | AI Confidence Distribution
  - Triage Levels         | RAG Retrieval Performance
  - Daily Volume          | Recent AI-Triaged Tickets
─────────────────────────────────────────
Footer
```

## Aggregate Cards

Each top-level card contains:
1. **Traffic light dot** — 10px circle, green `#0A7B3E` / amber `#B8860B` / red `#C8102E`
2. **Status label** — "On Track" / "Needs Attention" / "Critical"
3. **Hero metric** — large number, the most important metric from that category
4. **Hero sublabel** — what the number represents
5. **Left accent border** — 4px, category accent color

### Thresholds

| Category | Hero Metric | Source | Green | Amber | Red |
|---|---|---|---|---|---|
| Efficiency | Avg resolution time | `d.avgResolution` (parsed to hours) | < 24h | 24-48h | > 48h |
| Quality | FCR % | `d.fcr` | > 60% | 30-60% | < 30% |
| Customer Exp. | CSAT | `d.csat` | > 4.0 | 3.0-4.0 | < 3.0 |
| Support Intensity | Open tkt/agent | `openCount / agentCount` | < 15 | 15-25 | > 25 |
| Technical | Retrieval relevance | `d.avgKB` | > 0.7 | 0.4-0.7 | < 0.4 |

For demo metrics without live data, use the synthetic defaults to determine status.

### Parsing resolution time to hours

`d.avgResolution` is a string like `"2.4h"` or `"45m"`. Parse:
- If ends with `"m"`, divide by 60 to get hours
- If ends with `"h"`, parse the number directly
- If `"N/A"`, treat as amber

## Sub-KPI Sections

### Efficiency (accent: `#1A5276` blue, icon: "EFF")

| KPI | Value | Subtitle | Live? |
|---|---|---|---|
| Time to Resolution | `d.avgResolution` | Target: < 24h | LIVE |
| Time to Human Response | `d.avgResponse` | Target: < 12h | DEMO unless `!== "N/A"` |
| Agent Search Time | `"12s"` | Needs API timing logs | DEMO |
| Throughput per Agent | `"41.2"` | Needs agent assignment tracking | DEMO |

Grid: 4 columns.

### Quality (accent: `#0A7B3E` green, icon: "QTY")

| KPI | Value | Subtitle | Live? |
|---|---|---|---|
| First Contact Resolution | `d.fcr + "%"` | `d.fcrCount` of `d.triaged` resolved at L1 | LIVE |
| Reopen Rate | `"3.2%"` | Needs status transition tracking | DEMO |

Grid: 2 columns.

### Customer Experience (accent: `#7B2D8E` purple, icon: "CX")

| KPI | Value | Subtitle | Live? |
|---|---|---|---|
| Customer Satisfaction | `d.csat + "/5"` | `d.csatResponses` survey responses | LIVE if `csatResponses > 0` |
| Reopen Rate | `"3.2%"` | Needs status transition tracking | DEMO |

Grid: 2 columns.

### Support Intensity (accent: `#B8860B` amber, icon: "SI")

| KPI | Value | Subtitle | Live? |
|---|---|---|---|
| Open Tickets / Agent | `openCount / 5` (hardcoded 5 agents) | `openCount` open of `total` total | Partially LIVE |

Grid: 1 column (full width). Show the open count prominently. Agent count is hardcoded to 5 (no Jira API for team size).

### Technical (accent: `#3C3C3B` charcoal, icon: "TECH")

| KPI | Value | Subtitle | Live? |
|---|---|---|---|
| Human Override Rate | `"31.6%"` | Needs Forge send tracking | DEMO |
| Edit Distance | `"12%"` | Needs before/after text comparison | DEMO |
| Retrieval Relevance | `d.avgKB` | Avg KB cosine similarity | LIVE |
| Confidence Calibration | `"91%"` | Needs outcome correlation | DEMO |

Grid: 4 columns.

## Resolver Changes

Add to `getDashboardData` return:

```js
openCount: issues.filter(i => !i.fields.resolutiondate).length,
```

This counts tickets without a resolution date (still open).

## Color Palette

Category accent colors for section header icons and aggregate card left borders:

```js
const categoryColors = {
  efficiency: "#1A5276",    // blue
  quality: "#0A7B3E",       // green
  customerExp: "#7B2D8E",   // purple
  supportIntensity: "#B8860B", // amber
  technical: "#3C3C3B",     // charcoal
};
```

Traffic light colors (same for all categories):
- Green: `#0A7B3E`
- Amber: `#B8860B`
- Red: `#C8102E`

Background tints for aggregate cards:
- Green: `#E8F5EC`
- Amber: `#FFF8E1`
- Red: `#FDF0F1`

## Analytics Section

Keep existing charts unchanged:
- Tickets by Department (bar chart)
- AI Confidence Distribution (donut)
- Triage Level & Resolution Time (bar chart with L3 escalation warning)
- RAG Retrieval Performance (mini stats)
- Daily Ticket Volume (sparkline)
- Recent AI-Triaged Tickets (list with L3 badge)

## Removed from Current Dashboard

- "KPI" top section (5 mixed cards) → replaced by aggregate cards + Efficiency/Quality sections
- "Escalation" section (5 cards) → L3 count moves to Triage Level chart warning badge
- "AI Performance" section → renamed to "Technical"
- Duplicate metrics that appeared in multiple old sections

## Component Reuse

Reuse existing helper components: `section()`, `kpi()`, `bar()`, `ChartCard`, `SectionHeader`, `MiniStat`, `StatRow`, `Ticket`, `Leg`, `timeAgo`.

New component: `AggregateCard({ title, heroValue, heroLabel, status, accentColor })`.

`status` is computed from thresholds: `"green"` / `"amber"` / `"red"`.
