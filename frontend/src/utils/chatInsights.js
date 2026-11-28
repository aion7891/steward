// Pure helpers for the chat layout: step summaries, the latest scanned folder, suggestions.

/** The helpers that worked on an answer, in order, without "Steward" itself. */
export function helpersOf(steps) {
  const names = [];
  for (const step of steps || []) {
    if (step.agent && step.agent !== "Steward" && !names.includes(step.agent)) {
      names.push(step.agent);
    }
  }
  return names;
}

/** One line above an answer: "Worked 9 s · Scanner · 2 steps". */
export function stepSummary(steps, durationSec) {
  const list = steps || [];
  const parts = [];
  if (durationSec) {
    parts.push(`Worked ${durationSec < 60 ? `${Math.round(durationSec)} s` : `${Math.round(durationSec / 60)} min`}`);
  }
  const helpers = helpersOf(list);
  if (helpers.length) parts.push(helpers.join(", "));
  const tools = list.filter((s) => s.kind !== "handoff").length;
  if (tools || !parts.length) parts.push(`${tools} step${tools === 1 ? "" : "s"}`);
  const problems = list.filter((s) => s.status === "error").length;
  if (problems) parts.push(`${problems} problem${problems === 1 ? "" : "s"}`);
  return parts.join(" · ");
}

/** The newest folder card in the conversation, or null. */
export function latestFolder(messages) {
  for (let i = (messages || []).length - 1; i >= 0; i -= 1) {
    if (messages[i].folder) return messages[i].folder;
  }
  return null;
}

/** Approval cards in the conversation that still wait for a decision. */
export function pendingApprovals(messages) {
  return (messages || []).filter((m) => m.status === "approval" && !m.decision);
}

/** Steps to show under "Activity": the running answer's, else the last answer's. */
export function activitySteps(messages, job) {
  if (job && job.steps && job.steps.length) return job.steps;
  for (let i = (messages || []).length - 1; i >= 0; i -= 1) {
    if (messages[i].steps && messages[i].steps.length) return messages[i].steps;
  }
  return [];
}

function listOf(paths, max = 15) {
  return (paths || []).slice(0, max).join(", ");
}

/** The chat message a suggestion sends: it names the exact files, so the AI can act on them. */
export function suggestionPrompt(tip, folder) {
  const where = folder ? folder.path : "my files";
  const files = listOf(tip.paths);
  switch (tip.kind) {
    case "deduplicate":
      return `Move these duplicate copies to the recycle bin: ${files}`;
    case "clean_temp":
      return `Move these temporary files to the recycle bin: ${files}`;
    case "archive_stale":
      return `Archive these old files: ${files}`;
    case "review_large":
      return `Tell me about these large files and whether I still need them: ${files}`;
    case "group_folder":
      return `Organize the folder ${(tip.paths || [where])[0]} by file type`;
    default:
      return `${tip.title} in ${where}`;
  }
}
