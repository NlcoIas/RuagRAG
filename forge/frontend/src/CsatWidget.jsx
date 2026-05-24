import React, { useState, useEffect } from "react";
import { invoke, view } from "@forge/bridge";

view.theme.enable();

function CsatWidget() {
  const [loading, setLoading] = useState(true);
  const [isResolved, setIsResolved] = useState(false);
  const [rating, setRating] = useState(0);
  const [hover, setHover] = useState(0);
  const [comment, setComment] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const [alreadyRated, setAlreadyRated] = useState(false);
  const [existingRating, setExistingRating] = useState(0);

  useEffect(() => {
    invoke("getCsatData").then((data) => {
      if (data && data.isResolved !== undefined) {
        setIsResolved(data.isResolved);
        if (data.alreadyRated) {
          setAlreadyRated(true);
          setExistingRating(data.rating);
        }
      } else {
        // If resolver can't determine status, show the widget anyway
        setIsResolved(true);
      }
      setLoading(false);
    }).catch(() => {
      // On error, show widget anyway so customer can rate
      setIsResolved(true);
      setLoading(false);
    });
  }, []);

  const handleSubmit = async () => {
    if (rating === 0) return;
    const result = await invoke("submitCsat", { rating, comment: comment.trim() });
    if (result.success) {
      setSubmitted(true);
      setExistingRating(rating);
    }
  };

  if (loading) return <div style={styles.container}><p style={styles.muted}>Loading...</p></div>;
  if (!isResolved) return null; // Don't show on open tickets

  if (submitted || alreadyRated) {
    return (
      <div style={styles.container}>
        <div style={styles.thankYou}>
          <div style={styles.stars}>
            {[1,2,3,4,5].map(i => (
              <span key={i} style={{...styles.star, color: i <= existingRating ? "#E2B203" : "#DFE1E6"}}>{"\u2605"}</span>
            ))}
          </div>
          <p style={styles.thankText}>Thank you for your feedback!</p>
        </div>
      </div>
    );
  }

  return (
    <div style={styles.container}>
      <p style={styles.title}>How was your experience?</p>
      <div style={styles.stars}>
        {[1,2,3,4,5].map(i => (
          <span
            key={i}
            style={{
              ...styles.star,
              color: i <= (hover || rating) ? "#E2B203" : "#DFE1E6",
              cursor: "pointer",
            }}
            onClick={() => setRating(i)}
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(0)}
          >
            {"\u2605"}
          </span>
        ))}
      </div>
      {rating > 0 && (
        <>
          <textarea
            style={styles.textarea}
            placeholder="Any additional comments? (optional)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
          />
          <button style={styles.button} onClick={handleSubmit}>
            Submit feedback
          </button>
        </>
      )}
    </div>
  );
}

const styles = {
  container: {
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
    padding: "16px",
    minHeight: "50px",
  },
  title: {
    fontSize: "14px",
    fontWeight: 600,
    color: "#172B4D",
    marginBottom: "8px",
    margin: 0,
  },
  stars: {
    display: "flex",
    gap: "4px",
    margin: "8px 0",
  },
  star: {
    fontSize: "28px",
    transition: "color 0.15s",
    userSelect: "none",
  },
  textarea: {
    width: "100%",
    padding: "8px",
    border: "1px solid #DFE1E6",
    borderRadius: "4px",
    fontSize: "12px",
    fontFamily: "inherit",
    resize: "vertical",
    marginBottom: "8px",
    boxSizing: "border-box",
  },
  button: {
    background: "#0C66E4",
    color: "#fff",
    border: "none",
    borderRadius: "4px",
    padding: "8px 16px",
    fontSize: "12px",
    fontWeight: 600,
    cursor: "pointer",
    fontFamily: "inherit",
  },
  thankYou: {
    textAlign: "center",
  },
  thankText: {
    color: "#172B4D",
    fontSize: "13px",
    fontWeight: 500,
  },
  muted: {
    color: "#6B778C",
    fontSize: "12px",
  },
};

export default CsatWidget;
