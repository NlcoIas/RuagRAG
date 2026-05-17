import React from "react";
import { view } from "@forge/bridge";

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
  return (
    <div style={{fontFamily:"'Segoe UI',-apple-system,BlinkMacSystemFont,Roboto,sans-serif",background:R.bg,color:R.dark,padding:"24px",minHeight:"100px"}}>

      {/* Header with RUAG red bar */}
      <div style={{background:R.red,borderRadius:"8px 8px 0 0",padding:"16px 20px",display:"flex",justifyContent:"space-between",alignItems:"center",marginBottom:0}}>
        <div>
          <h1 style={{fontSize:"20px",color:R.white,margin:0,fontWeight:700}}>AI Support Dashboard</h1>
          <p style={{color:"rgba(255,255,255,0.7)",fontSize:"12px",marginTop:"2px"}}>Last 30 days · Project SUP · 247 tickets · Updated just now</p>
        </div>
        <div style={{fontSize:"22px",fontWeight:800,color:R.white,letterSpacing:"3px"}}>RUAG</div>
      </div>
      <div style={{height:3,background:"linear-gradient(90deg, #C8102E, #8B0A1E)",marginBottom:20}}></div>

      {section("KPI","Key Performance Indexes",R.red,[
        kpi("FCR (First Contact Resolution)","68.4%","159 of 231 resolved at L1 via AI",R.green,68.4),
        kpi("Avg Resolution Time","2.1h","Query to resolution",R.blue,91),
        kpi("RAG Hit Rate","74.2%","172 with score > 0.7",R.green,74.2),
        kpi("Classification Accuracy","89.1%","Department label match",R.amber,89.1),
        kpi("Triage Routing Accuracy","84.7%","Correct team assignment",R.amber,84.7),
      ],5)}

      {section("EFF","Efficiency",R.blue,[
        kpi("Time to Resolution","2.1h","Target: 48h · SLA: 96.8%",R.green),
        kpi("Time to Human Response","4.2m","Target: 12h · SLA: 97.6%",R.green),
        kpi("Agent Search Time","12s","AI triage: <30s avg",R.green),
        kpi("Throughput per Agent","41.2","Tickets/agent/month (+62% with AI)",R.blue),
      ],4)}

      {section("QTY","Quality",R.green,[
        kpi("First Contact Resolution","68.4%","L1 resolved without escalation",R.green),
        kpi("Customer Satisfaction","4.3/5","Based on 142 survey responses",R.green),
        kpi("Reopen Rate","3.2%","8 of 247 tickets reopened",R.green),
        kpi("Consistent Response Rate","94%","Same answer for similar queries",R.blue),
      ],4)}

      {section("ESC","Escalation",R.red,[
        kpi("Escalation Accuracy","84.7%","Correct level assignment",R.amber),
        kpi("Unnecessary Escalation","8.3%","L3 tickets solvable at L1/L2",R.green),
        kpi("Missed Escalation Rate","4.1%","L1/L2 tickets needing L3",R.amber),
        kpi("Escalation Resolution Time","18.4h","Avg for L3 tickets",R.blue),
      ],4)}

      {section("AI","AI Performance",R.charcoal,[
        kpi("Human Override Rate","31.6%","73 of 231 edited before send",R.blue),
        kpi("Suggestion Edit Distance","12%","Avg text change when edited",R.green),
        kpi("Retrieval Relevance","0.71","Avg cosine similarity",R.green),
        kpi("Confidence Calibration","91%","High-conf resolved without edit",R.green),
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
          {bar("L1 Self-Svc",104,231,R.green)}
          {bar("L2 Agent",88,231,R.blue)}
          {bar("L3 Expert",39,231,R.amber)}
          <div style={{marginTop:10,display:"flex",gap:14,fontSize:10,color:R.grayLight}}>
            <div><span style={{color:R.green,fontWeight:600}}>L1:</span> 8m avg</div>
            <div><span style={{color:R.blue,fontWeight:600}}>L2:</span> 2.4h avg</div>
            <div><span style={{color:R.amber,fontWeight:600}}>L3:</span> 18h avg</div>
          </div>
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
          <Ticket k="SUP-247" s="Cannot access SAP after password reset" d="IT" c="h" t="4m" />
          <Ticket k="SUP-246" s="Office 365 license renewal request" d="IT" c="m" t="12m" />
          <Ticket k="SUP-245" s="Parking badge not working at gate B" d="Facilities" c="h" t="28m" />
          <Ticket k="SUP-244" s="Need travel expense form for Q2" d="Finance" c="l" t="1h" />
          <Ticket k="SUP-243" s="New hire onboarding — laptop + VPN" d="HR" c="m" t="2h" />
          <Ticket k="SUP-242" s="VPN disconnecting after Win update" d="IT" c="h" t="3h" />
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

function kpi(name, value, sub, color, barPct) {
  return (
    <div key={name} style={{background:R.white,borderRadius:6,padding:12,border:`1px solid ${R.border}`,boxShadow:"0 1px 3px rgba(0,0,0,0.04)"}}>
      <div style={{fontSize:11,color:R.gray,marginBottom:4}}>{name}</div>
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

function Ticket({k, s, d, c, t}) {
  const bg = c==="h"?R.greenLight:c==="m"?R.amberLight:"#F5F5F5";
  const fg = c==="h"?R.green:c==="m"?R.amber:R.grayLight;
  const lbl = c==="h"?"High":c==="m"?"Med":"Low";
  return (
    <div style={{display:"flex",alignItems:"center",gap:8,padding:"5px 0",borderBottom:`1px solid ${R.border}`}}>
      <div style={{fontSize:10,color:R.red,fontWeight:600,width:52}}>{k}</div>
      <div style={{fontSize:10,color:R.dark,flex:1,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{s}</div>
      <div style={{fontSize:9,padding:"1px 5px",borderRadius:3,background:R.redLight,color:R.red}}>{d}</div>
      <div style={{fontSize:9,padding:"1px 5px",borderRadius:3,fontWeight:600,background:bg,color:fg}}>{lbl}</div>
      <div style={{fontSize:9,color:R.grayLight,width:36,textAlign:"right"}}>{t}</div>
    </div>
  );
}

export default Dashboard;
