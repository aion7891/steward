// A small coloured label, e.g. "Dry-run ON" or an action status.

// Map action/suggestion values to a colour so every page uses the same meaning
const TONES = {
  proposed: "warning",
  approved: "info",
  done: "success",
  undone: "neutral",
  rejected: "neutral",
  failed: "danger",
  blocked: "danger",
  high: "danger",
  medium: "warning",
  low: "info",
};

export function toneFor(value) {
  return TONES[String(value || "").toLowerCase()] || "neutral";
}

export default function Badge({ tone = "neutral", icon: Icon, children, title }) {
  return (
    <span className={`badge badge--${tone}`} title={title}>
      {Icon && <Icon size={12} aria-hidden="true" />}
      {children}
    </span>
  );
}
