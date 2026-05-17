import React, { useState, useEffect } from "react";
import { invoke } from "@forge/bridge";

function App() {
  const [loading, setLoading] = useState(true);
  const [issueKey, setIssueKey] = useState("");
  const [versions, setVersions] = useState([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [editedText, setEditedText] = useState("");
  const [metadata, setMetadata] = useState({});
  const [feedback, setFeedback] = useState("");
  const [refining, setRefining] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    invoke("getInitialData").then((data) => {
      setIssueKey(data.issueKey || "");
      setMetadata(data.metadata || {});
      const v = data.versions || [];
      setVersions(v);
      if (v.length > 0) {
        setCurrentIdx(v.length - 1);
        setEditedText(v[v.length - 1].text);
      }
      setLoading(false);
    });
  }, []);

  if (loading) {
    return <div className="panel-body loading">Loading suggestion...</div>;
  }

  if (versions.length === 0) {
    return (
      <div className="panel-body empty">
        No AI suggestion available for this ticket.
      </div>
    );
  }

  const handleVersionClick = (idx) => {
    setCurrentIdx(idx);
    setEditedText(versions[idx].text);
    setError("");
  };

  const handleRefine = async () => {
    if (!feedback.trim()) return;
    setRefining(true);
    setError("");

    const result = await invoke("refine", {
      currentText: editedText,
      feedback: feedback.trim(),
    });

    if (result.success) {
      const newVersion = {
        text: result.refined_text,
        feedback: feedback.trim(),
        timestamp: Date.now(),
      };
      const updated = [...versions, newVersion];
      setVersions(updated);
      setCurrentIdx(updated.length - 1);
      setEditedText(result.refined_text);
      setFeedback("");
    } else {
      setError(result.error || "Refinement failed. Try again.");
    }

    setRefining(false);
  };

  const handleSend = async () => {
    setError("");
    const result = await invoke("send", { text: editedText });
    if (result.success) {
      setSent(true);
    } else {
      setError(result.error || "Failed to send comment.");
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleRefine();
    }
  };

  // Build refinement log (skip v1 which has no feedback)
  const refinements = versions
    .map((v, i) => ({ ...v, idx: i }))
    .filter((v) => v.feedback);

  return (
    <div className="panel-body">
      {/* Version tabs */}
      <span className="label">Version</span>
      <div className="versions">
        {versions.map((v, i) => (
          <button
            key={i}
            className={`version-tab ${i === currentIdx ? "active" : ""}`}
            onClick={() => handleVersionClick(i)}
          >
            {i === 0 ? "v1 original" : `v${i + 1}${v.feedback ? ` "${v.feedback}"` : ""}`}
          </button>
        ))}
      </div>

      {/* Editable suggestion */}
      <span className="label">Suggested reply</span>
      <textarea
        className="suggestion-box"
        value={editedText}
        onChange={(e) => setEditedText(e.target.value)}
        disabled={sent}
      />
      <div className="edit-hint">Click to edit directly</div>

      {/* Metadata badges */}
      <div className="badges">
        {metadata.confidence && (
          <span className={`badge ${metadata.confidence === "High" ? "badge-green" : metadata.confidence === "Medium" ? "badge-yellow" : "badge-neutral"}`}>
            {metadata.confidence} confidence
          </span>
        )}
        {metadata.department && (
          <span className="badge badge-blue">{metadata.department}</span>
        )}
        {metadata.triageLevel && (
          <span className="badge badge-neutral">{metadata.triageLevel}</span>
        )}
        {metadata.kbScore > 0 && (
          <span className="badge badge-yellow">
            KB: {Number(metadata.kbScore).toFixed(2)}
          </span>
        )}
      </div>

      {/* Refinement log */}
      {refinements.length > 0 && (
        <>
          <span className="label">Refinement history</span>
          <div className="refine-log">
            {refinements.map((v) => (
              <div key={v.idx} className="refine-log-entry">
                <b>v{v.idx + 1}:</b> &ldquo;{v.feedback}&rdquo;
              </div>
            ))}
          </div>
        </>
      )}

      {/* Feedback + actions */}
      {!sent && (
        <>
          <span className="label">Refine with AI</span>
          <input
            className="feedback-input"
            placeholder="e.g. 'make it more direct', 'add a greeting'"
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={refining}
          />
          <div className="actions">
            <button
              className="btn btn-refine"
              onClick={handleRefine}
              disabled={refining || !feedback.trim()}
            >
              {refining ? "Refining..." : "Refine"}
            </button>
            <button className="btn btn-send" onClick={handleSend}>
              Send to Customer
            </button>
          </div>
        </>
      )}

      {sent && (
        <div className="success-banner">
          Comment posted to {issueKey}
        </div>
      )}

      {error && <div className="error-text">{error}</div>}
    </div>
  );
}

export default App;
