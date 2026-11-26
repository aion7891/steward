// One headline number on the dashboard (label, big value, small hint, icon).

export default function StatCard({ label, value, hint, icon: Icon, tone = "brand" }) {
  return (
    <div className={`card stat stat--${tone}`}>
      <div className="stat__top">
        <span>{label}</span>
        {Icon && (
          <span className="stat__icon">
            <Icon size={16} aria-hidden="true" />
          </span>
        )}
      </div>
      <div className="stat__value">{value}</div>
      {hint && <div className="stat__hint">{hint}</div>}
    </div>
  );
}
