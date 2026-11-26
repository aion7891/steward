// Coloured message box for errors, warnings and tips. Pass an ApiError as `error`.
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";

const ICONS = { danger: XCircle, warning: AlertTriangle, info: Info, success: CheckCircle2 };

export default function Alert({ tone = "info", title, error, children, action }) {
  const Icon = ICONS[tone] || Info;
  const message = error ? error.message || String(error) : children;
  return (
    <div className={`alert alert--${tone}`} role={tone === "danger" ? "alert" : "status"}>
      <Icon size={18} aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }} />
      <div style={{ flex: 1 }}>
        {title && <div className="alert__title">{title}</div>}
        <div>{message}</div>
      </div>
      {action}
    </div>
  );
}
