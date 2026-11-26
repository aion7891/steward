// A button with consistent styles. `loading` shows a spinner and blocks double clicks.
import Spinner from "./Spinner.jsx";

export default function Button({
  variant = "secondary",
  size = "md",
  icon: Icon,
  loading = false,
  disabled = false,
  type = "button",
  children,
  ...rest
}) {
  const classes = ["btn", `btn--${variant}`, size === "sm" ? "btn--sm" : ""].join(" ");
  return (
    <button type={type} className={classes} disabled={disabled || loading} {...rest}>
      {loading ? <Spinner /> : Icon && <Icon size={size === "sm" ? 14 : 16} aria-hidden="true" />}
      {children}
    </button>
  );
}
