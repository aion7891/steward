// Bar chart of files checked/changed per day, with the number of scans as a line.
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatShortDate } from "../../utils/format.js";
import Card from "../ui/Card.jsx";
import EmptyState from "../ui/EmptyState.jsx";

const AXIS_STYLE = { fontSize: 12, fill: "var(--color-text-faint)" };
const TOOLTIP_STYLE = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: 10,
  fontSize: 13,
};

export default function DailyChart({ daily }) {
  const hasActivity = daily.some((day) => day.scans > 0 || day.files_checked > 0);
  return (
    <Card title="Daily scan activity" subtitle={`Last ${daily.length} days (UTC)`}>
      {hasActivity ? (
        <div className="chart">
          <ResponsiveContainer width="100%" height={260}>
            <ComposedChart data={daily} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
              <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
              <XAxis dataKey="date" tickFormatter={formatShortDate} tick={AXIS_STYLE} axisLine={false} tickLine={false} />
              <YAxis yAxisId="files" tick={AXIS_STYLE} axisLine={false} tickLine={false} allowDecimals={false} />
              <YAxis yAxisId="scans" orientation="right" hide allowDecimals={false} />
              <Tooltip
                contentStyle={TOOLTIP_STYLE}
                labelFormatter={formatShortDate}
                cursor={{ fill: "var(--color-surface-muted)" }}
              />
              <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} />
              <Bar yAxisId="files" dataKey="files_checked" name="Files checked" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
              <Bar yAxisId="files" dataKey="files_changed" name="Files changed" fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
              <Line yAxisId="scans" dataKey="scans" name="Scans" stroke="var(--chart-3)" strokeWidth={2} dot={{ r: 3 }} type="linear" isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <EmptyState title="No scans in this period">
          Scans run every hour in the background, or start one from <strong>Scan a folder</strong>.
        </EmptyState>
      )}
    </Card>
  );
}
