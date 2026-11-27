// Friendly placeholder shown when a list has nothing in it yet.
import { Inbox } from "lucide-react";

export default function EmptyState({ icon: Icon = Inbox, title, children, action }) {
  return (
    <div className="empty">
      <div className="empty__icon">
        <Icon size={20} aria-hidden="true" />
      </div>
      {title && <div className="empty__title">{title}</div>}
      {children && <div>{children}</div>}
      {action}
    </div>
  );
}
