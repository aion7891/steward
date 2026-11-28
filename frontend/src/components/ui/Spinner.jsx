// Spinning circle for "working…" states, plus a centred Loading block.

export default function Spinner({ large = false }) {
  return <span className={`spinner ${large ? "spinner--lg" : ""}`} role="status" aria-label="Loading" />;
}

export function Loading({ label = "Loading…" }) {
  return (
    <div className="loading">
      <Spinner large />
      <span>{label}</span>
    </div>
  );
}
