// A white panel with an optional header (title, subtitle, actions on the right).

export default function Card({ title, subtitle, actions, children, className = "", bodyClassName = "" }) {
  const hasHeader = title || subtitle || actions;
  return (
    <section className={`card ${className}`}>
      {hasHeader && (
        <header className="card__header">
          <div>
            {title && <h3 className="card__title">{title}</h3>}
            {subtitle && <p className="card__subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="row">{actions}</div>}
        </header>
      )}
      <div className={`card__body ${bodyClassName}`}>{children}</div>
    </section>
  );
}
