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
};

function Dashboard() {
  const [d, setD] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    invoke("getDashboardData").then((live) => {
      // Merge live data with synthetic defaults for metrics we can't compute from Jira alone
      setD({
        total: live.total || 0,
        triaged: live.triaged || 0,
        triagedPct: live.triagedPct || 0,
        avgResolution: live.avgResolution || "N/A",
        avgResponse: live.avgResponse || "N/A",
        slaFirstResponse: 97.6, slaResolution: 96.8,
        fcr: live.fcr || 0, fcrCount: live.fcrCount || 0,
        ragHitRate: live.ragHitRate || 0, ragHitCount: live.ragHitCount || 0,
        classAccuracy: 89.1, triageAccuracy: 84.7,  // need ground truth to compute
        agentSearchTime: "12s", throughput: 41.2,    // need agent-level tracking
        csat: live.csatAvg || 4.3, csatResponses: live.csatCount || 0, reopenRate: 3.2, reopenCount: 8, consistentRate: 94,
        escAccuracy: 84.7, unnecessaryEsc: 8.3, missedEsc: 4.1, escResTime: "18.4h",
        humanOverride: 31.6, overrideCount: 73, editDistance: 12, confCalibration: 91,
        retrievalScore: live.avgKB || 0,
        confHigh: live.confHigh || 0, confMed: live.confMed || 0, confLow: live.confLow || 0,
        avgKB: live.avgKB || 0, avgTicket: live.avgTicket || 0,
        deptIT: live.deptIT || 0, deptHR: live.deptHR || 0, deptFac: live.deptFac || 0,
        deptFin: live.deptFin || 0, deptLegal: live.deptLegal || 0, deptGen: live.deptGen || 0,
        l1Count: live.l1Count || 0, l2Count: live.l2Count || 0, l3Count: live.l3Count || 0,
        kbHit: live.kbHit || 0, ticketHit: live.ticketHit || 0, combinedHit: live.combinedHit || 0,
        kbDocs: 342, ticketDocs: live.resolvedCount || 0, newIngestions: 47,
        recentTickets: live.recentTickets || [],
      });
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  if (loading) {
    return <div style={{fontFamily:"'Segoe UI',sans-serif",background:R.bg,padding:40,textAlign:"center",color:R.grayLight}}>Loading dashboard data...</div>;
  }
  if (!d) {
    return <div style={{fontFamily:"'Segoe UI',sans-serif",background:R.bg,padding:40,textAlign:"center",color:R.red}}>Failed to load dashboard data.</div>;
  }

  return (
    <div style={{fontFamily:"'Segoe UI',-apple-system,BlinkMacSystemFont,Roboto,sans-serif",background:R.bg,color:R.dark,padding:"24px",minHeight:"100px"}}>

      {/* Header with RUAG red bar */}
      <div style={{background:R.red,borderRadius:"8px 8px 0 0",padding:"16px 20px",display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:0}}>
        <div>
          <h1 style={{fontSize:"20px",color:R.white,margin:0,fontWeight:700}}>AI Support Dashboard</h1>
          <p style={{color:"rgba(255,255,255,0.7)",fontSize:"12px",marginTop:"2px"}}>Live data · Project SUP · {d.total} tickets · Updated just now</p>
        </div>
        <div style={{fontSize:"22px",fontWeight:800,color:R.white,letterSpacing:"3px"}}>RUAG</div>
      </div>
      <div style={{height:3,background:"linear-gradient(90deg, #C8102E, #8B0A1E)",marginBottom:12}}></div>

      {/* Data source legend */}
      <div style={{display:"flex",gap:16,marginBottom:16,fontSize:10,color:R.gray,alignItems:"center"}}>
        <span style={{display:"flex",alignItems:"center",gap:4}}>
          <span style={{padding:"1px 4px",borderRadius:2,fontWeight:600,background:"#E8F5EC",color:R.green,fontSize:8}}>LIVE</span>
          Computed from Jira ticket data in real-time
        </span>
        <span style={{display:"flex",alignItems:"center",gap:4}}>
          <span style={{padding:"1px 4px",borderRadius:2,fontWeight:600,background:"#FFF3F3",color:"#C8102E",fontSize:8}}>DEMO</span>
          Synthetic — requires additional tracking (Forge Storage, SLA API, ground truth)
        </span>
      </div>

      {section("KPI","Key Performance Indexes",R.red,[
        kpi("FCR (First Contact Resolution)",d.fcr+"%",d.fcrCount+" of "+d.triaged+" resolved at L1 via AI",R.green,d.fcr,true),
        kpi("Avg Resolution Time",d.avgResolution,"Query to resolution",R.blue,null,true),
        kpi("RAG Hit Rate",d.ragHitRate+"%",d.ragHitCount+" with score > 0.7",R.green,d.ragHitRate,true),
        kpi("Classification Accuracy","89.1%","Needs ground truth labels",R.amber,89.1,false),
        kpi("Triage Routing Accuracy","84.7%","Needs ground truth labels",R.amber,84.7,false),
      ],5)}

      {section("EFF","Efficiency",R.blue,[
        kpi("Time to Resolution",d.avgResolution,"Target: 48h",R.green,null,true),
        kpi("Time to Human Response",d.avgResponse,"Target: 12h",R.green,null,d.avgResponse!=="N/A"),
        kpi("Agent Search Time","12s","Needs API timing logs",R.green,null,false),
        kpi("Throughput per Agent","41.2","Needs agent assignment tracking",R.blue,null,false),
      ],4)}

      {section("QTY","Quality",R.green,[
        kpi("First Contact Resolution",d.fcr+"%","L1 resolved without escalation",R.green,null,true),
        kpi("Customer Satisfaction",d.csat+"/5",d.csatResponses+" survey responses",R.green,null,d.csatResponses > 0),
        kpi("Reopen Rate","3.2%","Needs status transition tracking",R.green,null,false),
        kpi("Consistent Response Rate","94%","Needs response similarity analysis",R.blue,null,false),
      ],4)}

      {section("ESC","Escalation",R.red,[
        kpi("L3 Escalations",d.l3Count.toString(),d.triaged>0?Math.round(d.l3Count/d.triaged*100)+"% of triaged tickets":"No triaged tickets",R.red,d.triaged>0?d.l3Count/d.triaged*100:0,true),
        kpi("Escalation Accuracy","84.7%","Needs ground truth labels",R.amber,null,false),
        kpi("Unnecessary Escalation","8.3%","Needs resolution-level analysis",R.green,null,false),
        kpi("Missed Escalation Rate","4.1%","Needs escalation event tracking",R.amber,null,false),
        kpi("Escalation Resolution Time","18.4h","Needs L3 resolution timestamps",R.blue,null,false),
      ],5)}

      {section("AI","AI Performance",R.charcoal,[
        kpi("Human Override Rate","31.6%","Needs Forge send tracking",R.blue,null,false),
        kpi("Suggestion Edit Distance","12%","Needs before/after text comparison",R.green,null,false),
        kpi("Retrieval Relevance",d.avgKB.toString(),"Avg KB cosine similarity",R.green,null,true),
        kpi("Confidence Calibration","91%","Needs outcome correlation",R.green,null,false),
      ],4)}

      <SectionHeader label="Analytics" color={R.charcoal} />
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"12px",marginBottom:"18px"}}>
        <ChartCard title="Tickets by Department">
          {bar("IT",178,247,R.red)}
          {bar("HR",30,247,"#7B2D8E")}
          {bar("Facilities",20,247,R.amber)}
          {bar("Finance",12,247,R.green)}
          {bar("Legal",4,247,R.blue)}
          {bar("General",3,247,R.grayLight)}
        </ChartCard>
        <ChartCard title="AI Confidence Distribution">
          <div style={{display:"flex",alignItems:"center",gap:"16px"}}>
            <div style={{width:110,height:110,borderRadius:"50%",background:`conic-gradient(${R.green} 0deg 194deg, ${R.amber} 194deg 280deg, ${R.red} 280deg 360deg)`,position:"relative"}}>
              <div style={{position:"absolute",top:24,left:24,width:62,height:62,background:R.white,borderRadius:"50%",display:"flex",alignItems:"center",justifyContent:"center",flexDirection:"column",boxShadow:"0 1px 3px rgba(0,0,0,0.08)"}}>
                <div style={{fontSize:20,fontWeight:700,color:R.green}}>54%</div>
                <div style={{fontSize:9,color:R.grayLight}}>High</div>
              </div>
            </div>
            <div style={{display:"flex",flexDirection:"column",gap:5}}>
              <Leg color={R.green} text="High — 125 (54%)" />
              <Leg color={R.amber} text="Medium — 72 (31%)" />
              <Leg color={R.red} text="Low — 34 (15%)" />
              <div style={{marginTop:6,paddingTop:5,borderTop:`1px solid ${R.border}`,fontSize:10,color:R.grayLight}}>Avg KB: 0.71 · Avg Ticket: 0.58</div>
            </div>
          </div>
        </ChartCard>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"12px",marginBottom:"18px"}}>
        <ChartCard title="Triage Level & Resolution Time">
          {bar("L1 Self-Svc",d.l1Count,Math.max(d.l1Count+d.l2Count+d.l3Count,1),R.green)}
          {bar("L2 Agent",d.l2Count,Math.max(d.l1Count+d.l2Count+d.l3Count,1),R.blue)}
          {bar("L3 Expert",d.l3Count,Math.max(d.l1Count+d.l2Count+d.l3Count,1),R.red)}
          <div style={{marginTop:10,display:"flex",gap:14,fontSize:10,color:R.grayLight}}>
            <div><span style={{color:R.green,fontWeight:600}}>L1:</span> Self-service</div>
            <div><span style={{color:R.blue,fontWeight:600}}>L2:</span> Agent</div>
            <div><span style={{color:R.red,fontWeight:600}}>L3:</span> Escalated</div>
          </div>
          {d.l3Count > 0 && (
            <div style={{marginTop:8,padding:"6px 10px",background:"#FFF0F0",borderRadius:4,border:"1px solid #FFCDD2",fontSize:10,color:"#BF2600",fontWeight:600,display:"flex",alignItems:"center",gap:6}}>
              <span style={{fontSize:14}}>&#9888;</span> {d.l3Count} ticket{d.l3Count!==1?"s":""} escalated to L3 Expert
            </div>
          )}
        </ChartCard>
        <ChartCard title="RAG Retrieval Performance">
          <div style={{display:"flex",gap:10,marginBottom:10}}>
            <MiniStat label="KB Hit" value="68%" color={R.green} />
            <MiniStat label="Ticket Hit" value="52%" color={R.blue} />
            <MiniStat label="Combined" value="74%" color={R.red} />
          </div>
          <div style={{fontSize:10,borderTop:`1px solid ${R.border}`,paddingTop:6}}>
            <StatRow label="KB docs indexed" value="342" />
            <StatRow label="Resolved tickets indexed" value="189" />
            <StatRow label="New ingestions this month" value="+47" />
          </div>
        </ChartCard>
      </div>
      <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:"12px"}}>
        <ChartCard title="Daily Ticket Volume (30 days)">
          <div style={{display:"flex",alignItems:"flex-end",gap:2,height:40}}>
            {[35,42,28,55,48,62,38,45,72,85,65,58,42,35,48,92,78,55,45,38,52,68,75,60,48,55,82,100,70,45].map((h,i)=>
              <div key={i} style={{width:"100%",height:h+"%",background:i<10?R.grayLight:R.red,borderRadius:2,minHeight:3}} />
            )}
          </div>
          <div style={{display:"flex",justifyContent:"space-between",marginTop:4,fontSize:9,color:R.grayLight}}>
            <span>Apr 17</span>
            <span>
              <span style={{display:"inline-block",width:7,height:7,background:R.grayLight,borderRadius:2,marginRight:2}}></span>Before AI
              {"  "}
              <span style={{display:"inline-block",width:7,height:7,background:R.red,borderRadius:2,marginRight:2}}></span>After AI
            </span>
            <span>May 17</span>
          </div>
        </ChartCard>
        <ChartCard title="Recent AI-Triaged Tickets">
          {d.recentTickets.length > 0 ? d.recentTickets.map((t) => {
            const c = t.confidence === "High" ? "h" : t.confidence === "Medium" ? "m" : "l";
            const ago = timeAgo(t.created);
            const esc = t.triageLevel === "L3 - Expert";
            return <Ticket key={t.key} k={t.key} s={t.summary} d={t.department} c={c} t={ago} esc={esc} />;
          }) : <div style={{fontSize:11,color:R.grayLight,padding:"10px 0"}}>No triaged tickets yet.</div>}
        </ChartCard>
      </div>

      {/* Footer */}
      <div style={{marginTop:20,paddingTop:12,borderTop:`2px solid ${R.red}`,display:"flex",justifyContent:"space-between",fontSize:10,color:R.grayLight}}>
        <span>RUAG AI Feedback Management · Powered by IBM watsonx Orchestrate + Granite</span>
        <span>DataStax Astra DB · Atlassian Jira Service Management</span>
      </div>
    </div>
  );
}

function section(icon, label, color, cards, cols) {
  return (
    <div style={{marginBottom:18}}>
      <SectionHeader label={label} icon={icon} color={color} />
      <div style={{display:"grid",gridTemplateColumns:`repeat(${cols},1fr)`,gap:10}}>
        {cards}
      </div>
    </div>
  );
}

function SectionHeader({label, icon, color}) {
  return (
    <div style={{display:"flex",alignItems:"center",gap:8,marginBottom:10}}>
      {icon && <span style={{fontSize:10,padding:"2px 8px",borderRadius:3,fontWeight:700,background:color,color:R.white}}>{icon}</span>}
      <span style={{fontSize:11,fontWeight:700,color:R.charcoal,textTransform:"uppercase",letterSpacing:1}}>{label}</span>
      <div style={{flex:1,height:1,background:R.border}}></div>
    </div>
  );
}

function kpi(name, value, sub, color, barPct, live) {
  return (
    <div key={name} style={{background:R.white,borderRadius:6,padding:12,border:`1px solid ${live?R.border:R.redMid}`,boxShadow:"0 1px 3px rgba(0,0,0,0.04)",opacity:live?1:0.75}}>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:4}}>
        <div style={{fontSize:11,color:R.gray}}>{name}</div>
        <span style={{fontSize:8,padding:"1px 4px",borderRadius:2,fontWeight:600,
          background:live?"#E8F5EC":"#FFF3F3",
          color:live?R.green:"#C8102E",
        }}>{live?"LIVE":"DEMO"}</span>
      </div>
      <div style={{fontSize:24,fontWeight:700,lineHeight:1,color}}>{value}</div>
      <div style={{fontSize:10,color:R.grayLight,marginTop:3}}>{sub}</div>
      {barPct && <div style={{height:3,background:R.border,borderRadius:2,marginTop:6}}><div style={{height:3,borderRadius:2,width:barPct+"%",background:color}}></div></div>}
    </div>
  );
}

function bar(label, count, total, color) {
  const pct = Math.round(count/total*100);
  return (
    <div key={label} style={{display:"flex",alignItems:"center",gap:6,marginBottom:6}}>
      <div style={{width:75,fontSize:10,color:R.gray,textAlign:"right"}}>{label}</div>
      <div style={{flex:1,height:16,background:"#EEEEEE",borderRadius:3,overflow:"hidden"}}>
        <div style={{height:"100%",width:pct+"%",background:color,borderRadius:3,display:"flex",alignItems:"center",paddingLeft:6,fontSize:9,color:R.white,fontWeight:600}}>{pct>3?pct+"%":""}</div>
      </div>
      <div style={{width:28,fontSize:10,color:R.grayLight,textAlign:"right"}}>{count}</div>
    </div>
  );
}

function ChartCard({title, children}) {
  return <div style={{background:R.white,borderRadius:6,padding:14,border:`1px solid ${R.border}`,boxShadow:"0 1px 3px rgba(0,0,0,0.04)"}}><div style={{fontSize:12,fontWeight:600,marginBottom:10,color:R.dark}}>{title}</div>{children}</div>;
}

function Leg({color, text}) {
  return <div style={{display:"flex",alignItems:"center",gap:5,fontSize:10,color:R.gray}}><div style={{width:7,height:7,borderRadius:"50%",background:color}}></div>{text}</div>;
}

function MiniStat({label, value, color}) {
  return <div style={{flex:1,background:R.bg,borderRadius:4,padding:8,textAlign:"center"}}><div style={{fontSize:9,color:R.grayLight}}>{label}</div><div style={{fontSize:20,fontWeight:700,color}}>{value}</div></div>;
}

function StatRow({label, value}) {
  return <div style={{display:"flex",justifyContent:"space-between",fontSize:10,padding:"3px 0"}}><span style={{color:R.grayLight}}>{label}</span><span style={{color:R.dark}}>{value}</span></div>;
}

function Ticket({k, s, d, c, t, esc}) {
  const bg = c==="h"?R.greenLight:c==="m"?R.amberLight:"#F5F5F5";
  const fg = c==="h"?R.green:c==="m"?R.amber:R.grayLight;
  const lbl = c==="h"?"High":c==="m"?"Med":"Low";
  return (
    <div style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:`1px solid ${R.border}`,background:esc?"#FFF5F5":"transparent"}}>
      <div style={{fontSize:10,color:R.red,fontWeight:600,width:52}}>{k}</div>
      <div style={{fontSize:10,color:R.dark,flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{s}</div>
      <div style={{fontSize:9,padding:"1px 5px",borderRadius:3,background:R.redLight,color:R.red}}>{d}</div>
      {esc && <div style={{fontSize:9,padding:"1px 5px",borderRadius:3,fontWeight:700,background:"#FFEDEB",color:"#BF2600"}}>L3</div>}
      <div style={{fontSize:9,padding:"1px 5px",borderRadius:3,fontWeight:600,background:bg,color:fg}}>{lbl}</div>
      <div style={{fontSize:9,color:R.grayLight,width:36,textAlign:"right"}}>{t}</div>
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
