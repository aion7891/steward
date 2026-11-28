// Collapsible lists of what the scan found: duplicates, temporary, old and large files.
import { formatBytes, formatRelativeTime, shortPath } from "../../utils/format.js";
import Badge from "../ui/Badge.jsx";
import Card from "../ui/Card.jsx";

function FileRow({ file, tag }) {
  return (
    <li className="file-row" title={file.path}>
      <div className="file-row__main">
        <div className="file-row__name">{file.name}</div>
        <div className="faint mono file-row__path">{shortPath(file.path, 4)}</div>
      </div>
      {tag}
      <span className="faint">{formatRelativeTime(file.modified_at)}</span>
      <span className="file-row__size">{formatBytes(file.size_bytes)}</span>
    </li>
  );
}

function Section({ title, hint, section, open, children }) {
  return (
    <details className="finding" open={open}>
      <summary className="finding__summary">
        <span className="finding__title">{title}</span>
        <Badge tone={section.count ? "warning" : "neutral"}>{section.count}</Badge>
        <span className="faint finding__hint">{hint}</span>
        <span className="finding__size">{formatBytes(section.total_bytes)}</span>
      </summary>
      {section.count === 0 ? <p className="faint finding__empty">Nothing found.</p> : children}
      {section.count > (section.items || []).length && (
        <p className="faint finding__empty">Showing the first {section.items.length} of {section.count}.</p>
      )}
    </details>
  );
}

export default function FindingsList({ findings }) {
  const dup = findings.duplicates;
  const lists = [
    ["temp_files", "Temporary files", "Half-finished downloads and scratch files"],
    ["stale_files", "Old files", "Not changed for a long time"],
    ["large_files", "Large files", "Biggest space users"],
  ];
  return (
    <Card title="What Steward found" subtitle="Only files inside this folder are listed.">
      <div className="findings">
        <Section title="Duplicates" hint={`${dup.extra_copies || 0} extra copies`} section={dup} open={dup.count > 0}>
          {dup.items.map((group) => (
            <ul key={group.sha256} className="file-list dup-group">
              {group.copies.map((file, index) => (
                <FileRow key={file.path} file={file}
                  tag={index === 0 ? <Badge tone="success">keep</Badge> : <Badge tone="warning">extra copy</Badge>} />
              ))}
            </ul>
          ))}
        </Section>
        {lists.map(([key, title, hint]) => (
          <Section key={key} title={title} hint={hint} section={findings[key]} open={false}>
            <ul className="file-list">
              {findings[key].items.map((file) => <FileRow key={file.path} file={file} />)}
            </ul>
          </Section>
        ))}
      </div>
    </Card>
  );
}
