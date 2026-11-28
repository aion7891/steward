// A white panel with an optional header (title, subtitle, actions on the right). `collapsed`
// shows only the header (used by cards that can be folded).

export default function Card({ title, subtitle, actions, children, className = "", bodyClassName = "", collapsed = false, id }) {
  const hasHeader = title || subtitle || actions;
  return (
    <section id={id} className={`card ${collapsed ? "card--collapsed" : ""} ${className}`}>
      {hasHeader && (
        <header className="card__header">
          <div>
            {title && <h3 className="card__title">{title}</h3>}
            {subtitle && <p className="card__subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      {!collapsed && <div className={`card__body ${bodyClassName}`}>{children}</div>}
    </section>
  );
}
