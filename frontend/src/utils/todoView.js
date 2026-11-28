// Plain helpers for the Dashboard To-do card (kept separate so they are easy to test).
export const TODO_LIMIT = 10;

/** The to-do items to show: the first `limit` ones, or all when showAll is on (or no limit is set). */
export function visibleTodo(todo, showAll, limit = TODO_LIMIT) {
  const items = todo || [];
  return showAll || !limit ? items : items.slice(0, limit);
}

/** The subtitle of the folded card (the badge already shows how many are open). */
export function todoSummary(todo, waiting) {
  const count = (waiting || []).length;
  if (count) return `Folded · ${count} approved, waiting to run`;
  return (todo || []).length ? "Folded · click Show to see the list" : "Nothing waiting for your decision";
}
