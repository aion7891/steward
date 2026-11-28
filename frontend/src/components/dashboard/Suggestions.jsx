// Prioritised cleanup suggestions (high / medium / low) with the space each could free.
import { FolderSearch, Sparkles } from "lucide-react";
import { Link } from "react-router-dom";

import { formatBytes, shortPath } from "../../utils/format.js";
import Badge, { toneFor } from "../ui/Badge.jsx";
import Card from "../ui/Card.jsx";
import EmptyState from "../ui/EmptyState.jsx";

const MB = 1024 * 1024;

export default function Suggestions({ suggestions, subtitle = "Based on the latest scans", showScanLink = true }) {
  const scanLink = (
    <Link to="/scan" className="btn btn--sm btn--secondary">
      <FolderSearch size={14} aria-hidden="true" /> Scan a folder
    </Link>
  );
  return (
    <Card title="Suggestions" subtitle={subtitle} actions={showScanLink ? scanLink : null}>
      {suggestions.length === 0 ? (
        <EmptyState icon={Sparkles} title="Nothing to suggest">
          Your scanned folders look tidy.
        </EmptyState>
      ) : (
        <ul className="suggestion-list">
          {suggestions.map((item, index) => (
            <li key={`${item.kind}-${index}`} className="suggestion">
              <Badge tone={toneFor(item.priority)}>{item.priority}</Badge>
              <div className="suggestion__main">
                <div className="suggestion__title">{item.title}</div>
                <div className="faint">{item.reason}</div>
                {item.paths && item.paths.length > 0 && (
                  <div className="faint mono suggestion__paths" title={item.paths.join("\n")}>
                    {item.paths.slice(0, 2).map((p) => shortPath(p, 3)).join(", ")}
                    {item.paths.length > 2 && ` +${item.paths.length - 2} more`}
                  </div>
                )}
              </div>
              {item.reclaimable_mb > 0 && <span className="suggestion__size">{formatBytes(item.reclaimable_mb * MB)}</span>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
