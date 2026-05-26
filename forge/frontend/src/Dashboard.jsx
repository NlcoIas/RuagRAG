import React, { useState, useEffect } from "react";
import { invoke, view } from "@forge/bridge";

view.theme.enable();

// RUAG Brand Colors
const R = {
  red: "#C8102E",
  redLight: "#FDF0F1",
  redMid: "#E8B4BB",
  dark: "#1D1D1B",
  charcoal: "#3C3C3B",
  gray: "#6B6B6B",
  grayLight: "#9E9E9E",
  border: "#E5E5E5",
  bg: "#F5F5F5",
  white: "#FFFFFF",
  green: "#0A7B3E",
  greenLight: "#E8F5EC",
  blue: "#1A5276",
  blueLight: "#E8F0F7",
  amber: "#B8860B",
  amberLight: "#FFF8E1",
  purple: "#7B2D8E",
  purpleLight: "#F3E8F7",
};

// Category accent colors
const CAT = {
  efficiency: R.blue,
  quality: R.green,
  customerExp: R.purple,
  supportIntensity: R.amber,
  technical: R.charcoal,
};

// Traffic light backgrounds
const STATUS_BG = { green: R.greenLight, amber: R.amberLight, red: R.redLight };
const STATUS_FG = { green: R.green, amber: R.amber, red: R.red };
const STATUS_LABEL = { green: "On Track", amber: "Needs Attention", red: "Critical" };

function parseResolutionHours(str) {
  if (!str || str === "N/A") return null;
  if (str.endsWith("m")) return parseFloat(str) / 60;
  if (str.endsWith("h")) return parseFloat(str);
  return null;
}

function getStatus(value, greenMax, amberMax) {
  if (value == null) return "amber";
  if (value <= greenMax) return "green";
  if (value <= amberMax) return "amber";
  return "red";
}

function getStatusInverse(value, greenMin, amberMin) {
  if (value == null) return "amber";
  if (value >= greenMin) return "green";
  if (value >= amberMin) return "amber";
  return "red";
}

function Dashboard() {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    invoke("getDashboardData").then((live) => {
      setD({
        total: live.total || 0,
        triaged: live.triaged || 0,
        triagedPct: live.triagedPct || 0,
        avgResolution: live.avgResolution || "N/A",
        avgResponse: live.avgResponse || "N/A",
        fcr: live.fcr || 0, fcrCount: live.fcrCount || 0,
        ragHitRate: live.ragHitRate || 0, ragHitCount: live.ragHitCount || 0,
        csat: live.csatAvg || 4.1, csatResponses: live.csatCount || 0,
        reopenRate: 4.8,
        agentSearchTime: "8s", throughput: 34.7,
        humanOverride: 24.3, editDistance: 18, confCalibration: 87,
        avgKB: live.avgKB || 0, avgTicket: live.avgTicket || 0,
        confHigh: live.confHigh || 0, confMed: live.confMed || 0, confLow: live.confLow || 0,
        deptIT: live.deptIT || 0, deptHR: live.deptHR || 0, deptFac: live.deptFac || 0,
        deptFin: live.deptFin || 0, deptLegal: live.deptLegal || 0, deptGen: live.deptGen || 0,
        l1Count: live.l1Count || 0, l2Count: live.l2Count || 0, l3Count: live.l3Count || 0,
        kbHit: live.kbHit || 0, ticketHit: live.ticketHit || 0, combinedHit: live.combinedHit || 0,
        kbDocs: 342, ticketDocs: live.resolvedCount || 0,
        openCount: live.openCount || 0,
        recentTickets: live.recentTickets || [],
      });
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) return <div style={{fontFamily:"'Segoe UI',sans-serif",background:R.bg,padding:40,textAlign:"center",color:R.grayLight,minHeight:"2000px"}}>Loading dashboard data...</div>;
  if (!d) return <div style={{fontFamily:"'Segoe UI',sans-serif",background:R.bg,padding:40,textAlign:"center",color:R.red}}>Failed to load dashboard data.</div>;

  // Compute aggregate statuses
  const resHours = parseResolutionHours(d.avgResolution);
  const effStatus = getStatus(resHours, 24, 48);
  const qtyStatus = getStatusInverse(d.fcr, 60, 30);
  const cxStatus = getStatusInverse(d.csat, 4.0, 3.0);
  const agentCount = 5;
  const ticketsPerAgent = d.openCount / agentCount;
  const siStatus = getStatus(ticketsPerAgent, 15, 25);
  const techStatus = getStatusInverse(d.avgKB, 0.7, 0.4);

  return (
    <div style={{fontFamily:"'Segoe UI',-apple-system,BlinkMacSystemFont,Roboto,sans-serif",background:R.bg,color:R.dark,padding:"24px",minHeight:"100px"}}>

      {/* Header */}
      <div style={{background:R.red,borderRadius:"8px 8px 0 0",padding:"16px 20px",display:"flex",justifyContent:"space-between",alignItems:"center"}}>
        <div>
          <h1 style={{fontSize:"20px",color:R.white,margin:0,fontWeight:700}}>AI Support Dashboard</h1>
          <p style={{color:"rgba(255,255,255,0.7)",fontSize:"12px",marginTop:"2px"}}>Live data &middot; Project SUP &middot; {d.total} tickets &middot; Updated just now</p>
        </div>
        <div style={{fontSize:"22px",fontWeight:800,color:R.white,letterSpacing:"3px"}}>RUAG</div>
      </div>
      <div style={{height:3,background:"linear-gradient(90deg, #C8102E, #8B0A1E)",marginBottom:12}} />

      {/* Legend */}
      <div style={{display:"flex",gap:16,marginBottom:16,fontSize:10,color:R.gray,alignItems:"center"}}>
        <span style={{display:"flex",alignItems:"center",gap:4}}>
          <span style={{padding:"1px 4px",borderRadius:2,fontWeight:600,background:R.greenLight,color:R.green,fontSize:8}}>LIVE</span>
          Computed from Jira data
        </span>
        <span style={{display:"flex",alignItems:"center",gap:4}}>
          <span style={{padding:"1px 4px",borderRadius:2,fontWeight:600,background:R.redLight,color:R.red,fontSize:8}}>DEMO</span>
          Synthetic — needs additional tracking
        </span>
      </div>

      {/* ═══ TOP-LEVEL AGGREGATE CARDS ═══ */}
      <div style={{display:"grid",gridTemplateColumns:"repeat(5,1fr)",gap:10,marginBottom:20}}>
        <AggregateCard title="Efficiency" heroValue={d.avgResolution} heroLabel="avg resolution" status={effStatus} accent={CAT.efficiency} />
        <AggregateCard title="Quality" heroValue={d.fcr + "%"} heroLabel="first contact res." status={qtyStatus} accent={CAT.quality} />
        <AggregateCard title="Customer Exp." heroValue={d.csat + "/5"} heroLabel="satisfaction" status={cxStatus} accent={CAT.customerExp} />
        <AggregateCard title="Support Intensity" heroValue={ticketsPerAgent.toFixed(1)} heroLabel="tickets / agent" status={siStatus} accent={CAT.supportIntensity} />
        <AggregateCard title="Technical" heroValue={d.avgKB.toFixed(2)} heroLabel="retrieval score" status={techStatus} accent={CAT.technical} />
      </div>

      {/* ═══ EFFICIENCY ═══ */}
      {section("EFF", "Efficiency", CAT.efficiency, [
        kpi("Time to Resolution", d.avgResolution, "Created to resolved · Target < 24h", CAT.efficiency, null, true),
        kpi("Time to Human Response", d.avgResponse, "First agent reply · Target < 12h", CAT.efficiency, null, d.avgResponse !== "N/A"),
        kpi("Agent Search Time", d.agentSearchTime, "Avg time to find relevant info", R.grayLight, null, false),
        kpi("Throughput per Agent", d.throughput.toString(), "Tickets handled per agent / month", R.grayLight, null, false),
      ], 4)}

      {/* ═══ QUALITY ═══ */}
      {section("QTY", "Quality", CAT.quality, [
        kpi("First Contact Resolution", d.fcr + "%", d.fcrCount + " of " + d.triaged + " resolved at L1", CAT.quality, d.fcr, true),
        kpi("Reopen Rate", d.reopenRate + "%", "Tickets reopened after resolution", R.grayLight, null, false),
      ], 2)}

      {/* ═══ CUSTOMER EXPERIENCE ═══ */}
      {section("CX", "Customer Experience", CAT.customerExp, [
        kpi("Customer Satisfaction", d.csat + "/5", d.csatResponses + " survey responses", CAT.customerExp, null, d.csatResponses > 0),
      ], 1)}

      {/* ═══ SUPPORT INTENSITY ═══ */}
      {section("SI", "Support Intensity", CAT.supportIntensity, [
        kpi("Open Tickets / Agent", ticketsPerAgent.toFixed(1), d.openCount + " open of " + d.total + " total (" + agentCount + " agents)", CAT.supportIntensity, null, true),
      ], 1)}

      {/* ═══ TECHNICAL ═══ */}
      {section("TECH", "Technical", CAT.technical, [
        kpi("Human Override Rate", d.humanOverride + "%", "Agent edits AI suggestion before sending", R.grayLight, null, false),
        kpi("Edit Distance", d.editDistance + "%", "Avg change between AI draft and sent text", R.grayLight, null, false),
        kpi("Retrieval Relevance", d.avgKB.toFixed(2), "Avg KB cosine similarity · Target > 0.7", CAT.technical, null, true),
        kpi("Confidence Calibration", d.confCalibration + "%", "AI confidence vs actual resolution accuracy", R.grayLight, null, false),
      ], 4)}

      {/* ═══ ANALYTICS ═══ */}
      <SectionHeader label="Analytics" color={R.charcoal} />
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"12px",marginBottom:"18px"}}>
        <ChartCard title="Tickets by Department">
          {bar("IT", d.deptIT, Math.max(d.triaged, 1), R.red)}
          {bar("HR", d.deptHR, Math.max(d.triaged, 1), R.purple)}
          {bar("Facilities", d.deptFac, Math.max(d.triaged, 1), R.amber)}
          {bar("Finance", d.deptFin, Math.max(d.triaged, 1), R.green)}
          {bar("Legal", d.deptLegal, Math.max(d.triaged, 1), R.blue)}
          {bar("General", d.deptGen, Math.max(d.triaged, 1), R.grayLight)}
        </ChartCard>
        <ChartCard title="AI Confidence Distribution">
          <div style={{display:"flex",alignItems:"center",gap:"16px"}}>
            {(() => {
              const tot = d.confHigh + d.confMed + d.confLow || 1;
              const hPct = Math.round(d.confHigh / tot * 100);
              const mPct = Math.round(d.confMed / tot * 100);
              const hDeg = Math.round(d.confHigh / tot * 360);
              const mDeg = hDeg + Math.round(d.confMed / tot * 360);
              return (
                <>
                  <div style={{width:100,height:100,borderRadius:"50%",background:`conic-gradient(${R.green} 0deg ${hDeg}deg, ${R.amber} ${hDeg}deg ${mDeg}deg, ${R.red} ${mDeg}deg 360deg)`,position:"relative",flexShrink:0}}>
                    <div style={{position:"absolute",top:22,left:22,width:56,height:56,background:R.white,borderRadius:"50%",display:"flex",alignItems:"center",justifyContent:"center",flexDirection:"column",boxShadow:"0 1px 3px rgba(0,0,0,0.08)"}}>
                      <div style={{fontSize:18,fontWeight:700,color:R.green}}>{hPct}%</div>
                      <div style={{fontSize:8,color:R.grayLight}}>High</div>
                    </div>
                  </div>
                  <div style={{display:"flex",flexDirection:"column",gap:4}}>
                    <Leg color={R.green} text={`High — ${d.confHigh} (${hPct}%)`} />
                    <Leg color={R.amber} text={`Medium — ${d.confMed} (${mPct}%)`} />
                    <Leg color={R.red} text={`Low — ${d.confLow} (${100 - hPct - mPct}%)`} />
                    <div style={{marginTop:4,paddingTop:4,borderTop:`1px solid ${R.border}`,fontSize:10,color:R.grayLight}}>Avg KB: {d.avgKB.toFixed(2)} &middot; Avg Ticket: {d.avgTicket.toFixed(2)}</div>
                  </div>
                </>
              );
            })()}
          </div>
        </ChartCard>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"12px",marginBottom:"18px"}}>
        <ChartCard title="Triage Level Distribution">
          {bar("L1 Self-Svc", d.l1Count, Math.max(d.l1Count + d.l2Count + d.l3Count, 1), R.green)}
          {bar("L2 Agent", d.l2Count, Math.max(d.l1Count + d.l2Count + d.l3Count, 1), R.blue)}
          {bar("L3 Expert", d.l3Count, Math.max(d.l1Count + d.l2Count + d.l3Count, 1), R.red)}
          <div style={{marginTop:8,display:"flex",gap:12,fontSize:10,color:R.grayLight}}>
            <div><span style={{color:R.green,fontWeight:600}}>L1:</span> Self-service</div>
            <div><span style={{color:R.blue,fontWeight:600}}>L2:</span> Agent</div>
            <div><span style={{color:R.red,fontWeight:600}}>L3:</span> Escalated</div>
          </div>
          {d.l3Count > 0 && (
            <div style={{marginTop:6,padding:"5px 8px",background:R.redLight,borderRadius:3,border:`1px solid ${R.redMid}`,fontSize:10,color:R.red,fontWeight:600,display:"flex",alignItems:"center",gap:5}}>
              <span style={{fontSize:13}}>&#9888;</span> {d.l3Count} ticket{d.l3Count !== 1 ? "s" : ""} escalated to L3
            </div>
          )}
        </ChartCard>
        <ChartCard title="RAG Retrieval Performance">
          <div style={{display:"flex",gap:8,marginBottom:8}}>
            <MiniStat label="KB Hit" value={d.kbHit + "%"} color={R.green} />
            <MiniStat label="Ticket Hit" value={d.ticketHit + "%"} color={R.blue} />
            <MiniStat label="Combined" value={d.combinedHit + "%"} color={R.red} />
          </div>
          <div style={{fontSize:10,borderTop:`1px solid ${R.border}`,paddingTop:5}}>
            <StatRow label="KB docs indexed" value={d.kbDocs.toString()} />
            <StatRow label="Resolved tickets" value={d.ticketDocs.toString()} />
          </div>
        </ChartCard>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"12px"}}>
        <ChartCard title="Daily Ticket Volume (30 days)">
          <div style={{display:"flex",alignItems:"flex-end",gap:2,height:40}}>
            {[35,42,28,55,48,62,38,45,72,85,65,58,42,35,48,92,78,55,45,38,52,68,75,60,48,55,82,100,70,45].map((h, i) =>
              <div key={i} style={{width:"100%",height:h+"%",background:i < 10 ? R.grayLight : R.red,borderRadius:2,minHeight:3}} />
            )}
          </div>
          <div style={{display:"flex",justifyContent:"space-between",marginTop:4,fontSize:9,color:R.grayLight}}>
            <span>Apr 17</span>
            <span>
              <span style={{display:"inline-block",width:7,height:7,background:R.grayLight,borderRadius:2,marginRight:2}} />Before AI
              {"  "}
              <span style={{display:"inline-block",width:7,height:7,background:R.red,borderRadius:2,marginRight:2}} />After AI
            </span>
            <span>May 17</span>
          </div>
        </ChartCard>
        <ChartCard title="Recent AI-Triaged Tickets">
          {d.recentTickets.length > 0 ? d.recentTickets.map((t) => {
            const c = t.confidence === "High" ? "h" : t.confidence === "Medium" ? "m" : "l";
            const ago = timeAgo(t.created);
            const esc = t.triageLevel === "L3 - Expert";
            return <TicketRow key={t.key} k={t.key} s={t.summary} d={t.department} c={c} t={ago} esc={esc} />;
          }) : <div style={{fontSize:11,color:R.grayLight,padding:"10px 0"}}>No triaged tickets yet.</div>}
        </ChartCard>
      </div>

      {/* Footer */}
      <div style={{marginTop:20,paddingTop:12,borderTop:`2px solid ${R.red}`,display:"flex",justifyContent:"space-between",fontSize:10,color:R.grayLight}}>
        <span>RUAG AI Feedback Management &middot; IBM watsonx Orchestrate + Granite</span>
        <span>DataStax Astra DB &middot; Atlassian Jira Service Management</span>
      </div>
    </div>
  );
}

/* ═══════════════ COMPONENTS ═══════════════ */

function AggregateCard({ title, heroValue, heroLabel, status, accent }) {
  const dotColor = STATUS_FG[status];
  const bg = STATUS_BG[status];
  const label = STATUS_LABEL[status];
  return (
    <div style={{
      background: R.white, borderRadius: 8, padding: "14px 16px",
      borderLeft: `4px solid ${accent}`,
      border: `1px solid ${R.border}`,
      borderLeftColor: accent, borderLeftWidth: 4, borderLeftStyle: "solid",
      boxShadow: "0 2px 6px rgba(0,0,0,0.05)",
    }}>
      <div style={{display:"flex",alignItems:"center",gap:6,marginBottom:8}}>
        <div style={{width:10,height:10,borderRadius:"50%",background:dotColor,flexShrink:0}} />
        <span style={{fontSize:10,fontWeight:600,color:dotColor,padding:"1px 6px",borderRadius:3,background:bg}}>{label}</span>
      </div>
      <div style={{fontSize:28,fontWeight:700,lineHeight:1,color:R.dark,marginBottom:2}}>{heroValue}</div>
      <div style={{fontSize:10,color:R.grayLight}}>{heroLabel}</div>
      <div style={{fontSize:10,fontWeight:600,color:accent,marginTop:6,textTransform:"uppercase",letterSpacing:0.5}}>{title}</div>
    </div>
  );
}

function section(icon, label, color, cards, cols) {
  return (
    <div style={{marginBottom:16}}>
      <SectionHeader label={label} icon={icon} color={color} />
      <div style={{display:"grid",gridTemplateColumns:`repeat(${cols},1fr)`,gap:10}}>
        {cards}
      </div>
    </div>
  );
}

function SectionHeader({ label, icon, color }) {
  return (
    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:8}}>
      {icon && <span style={{fontSize:9,padding:"2px 7px",borderRadius:3,fontWeight:700,background:color,color:R.white}}>{icon}</span>}
      <span style={{fontSize:11,fontWeight:700,color:R.charcoal,textTransform:"uppercase",letterSpacing:1}}>{label}</span>
      <div style={{flex:1,height:1,background:R.border}} />
    </div>
  );
}

function kpi(name, value, sub, color, barPct, live) {
  return (
    <div key={name} style={{
      background: R.white, borderRadius: 6, padding: 12,
      border: `1px solid ${live ? R.border : R.redMid}`,
      boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
      opacity: live ? 1 : 0.7,
    }}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}>
        <div style={{fontSize:11,color:R.gray}}>{name}</div>
        <span style={{
          fontSize:8, padding:"1px 4px", borderRadius:2, fontWeight:600,
          background: live ? R.greenLight : R.redLight,
          color: live ? R.green : R.red,
        }}>{live ? "LIVE" : "DEMO"}</span>
      </div>
      <div style={{fontSize:22,fontWeight:700,lineHeight:1,color}}>{value}</div>
      <div style={{fontSize:10,color:R.grayLight,marginTop:3}}>{sub}</div>
      {barPct != null && <div style={{height:3,background:R.border,borderRadius:2,marginTop:6}}><div style={{height:3,borderRadius:2,width:Math.min(barPct, 100)+"%",background:color}} /></div>}
    </div>
  );
}

function bar(label, count, total, color) {
  const pct = total > 0 ? Math.round(count / total * 100) : 0;
  return (
    <div key={label} style={{display:"flex",alignItems:"center",gap:6,marginBottom:5}}>
      <div style={{width:70,fontSize:10,color:R.gray,textAlign:"right"}}>{label}</div>
      <div style={{flex:1,height:15,background:"#EEEEEE",borderRadius:3,overflow:"hidden"}}>
        <div style={{height:"100%",width:pct+"%",background:color,borderRadius:3,display:"flex",alignItems:"center",paddingLeft:5,fontSize:9,color:R.white,fontWeight:600}}>{pct > 5 ? pct+"%" : ""}</div>
      </div>
      <div style={{width:26,fontSize:10,color:R.grayLight,textAlign:"right"}}>{count}</div>
    </div>
  );
}

function ChartCard({ title, children }) {
  return (
    <div style={{background:R.white,borderRadius:6,padding:14,border:`1px solid ${R.border}`,boxShadow:"0 1px 3px rgba(0,0,0,0.04)"}}>
      <div style={{fontSize:12,fontWeight:600,marginBottom:10,color:R.dark}}>{title}</div>
      {children}
    </div>
  );
}

function Leg({ color, text }) {
  return <div style={{display:"flex",alignItems:"center",gap:5,fontSize:10,color:R.gray}}><div style={{width:7,height:7,borderRadius:"50%",background:color}} />{text}</div>;
}

function MiniStat({ label, value, color }) {
  return <div style={{flex:1,background:R.bg,borderRadius:4,padding:8,textAlign:"center"}}><div style={{fontSize:9,color:R.grayLight}}>{label}</div><div style={{fontSize:18,fontWeight:700,color}}>{value}</div></div>;
}

function StatRow({ label, value }) {
  return <div style={{display:"flex",justifyContent:"space-between",fontSize:10,padding:"2px 0"}}><span style={{color:R.grayLight}}>{label}</span><span style={{color:R.dark}}>{value}</span></div>;
}

function TicketRow({ k, s, d, c, t, esc }) {
  const bg = c === "h" ? R.greenLight : c === "m" ? R.amberLight : "#F5F5F5";
  const fg = c === "h" ? R.green : c === "m" ? R.amber : R.grayLight;
  const lbl = c === "h" ? "High" : c === "m" ? "Med" : "Low";
  return (
    <div style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:`1px solid ${R.border}`,background:esc ? R.redLight : "transparent"}}>
      <div style={{fontSize:10,color:R.red,fontWeight:600,width:50}}>{k}</div>
      <div style={{fontSize:10,color:R.dark,flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{s}</div>
      <div style={{fontSize:9,padding:"1px 5px",borderRadius:3,background:R.redLight,color:R.red}}>{d}</div>
      {esc && <div style={{fontSize:9,padding:"1px 5px",borderRadius:3,fontWeight:700,background:"#FFEDEB",color:"#BF2600"}}>L3</div>}
      <div style={{fontSize:9,padding:"1px 5px",borderRadius:3,fontWeight:600,background:bg,color:fg}}>{lbl}</div>
      <div style={{fontSize:9,color:R.grayLight,width:34,textAlign:"right"}}>{t}</div>
    </div>
  );
}

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return mins + "m";
  const hours = Math.floor(mins / 60);
  if (hours < 24) return hours + "h";
  return Math.floor(hours / 24) + "d";
}

export default Dashboard;
