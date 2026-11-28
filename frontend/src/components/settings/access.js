// Whether Steward may change files in a watched folder, as a badge and a plain-language hint.

/** Return {tone, label, title} for a folder's write-access badge, or null for unknown/missing folders. */
export function accessBadge(folder) {
  if (!folder || !folder.available) {
    return null;
  }
  if (folder.writable) {
    return { tone: "success", label: "writable", title: "Steward can move, archive or recycle files here (after your approval)." };
  }
  const how = folder.access_var ? ` Set ${folder.access_var}=rw in .env to allow changes.` : "";
  return { tone: "neutral", label: "read-only", title: `Steward can scan and suggest here, but not change files.${how}` };
}

/** Return the .env switches that would make the read-only folders writable (no duplicates). */
export function readOnlySwitches(folders) {
  const names = (folders || [])
    .filter((f) => f && f.available && !f.writable && f.access_var)
    .map((f) => f.access_var);
  return [...new Set(names)];
}
