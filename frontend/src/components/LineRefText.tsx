import { Link } from "react-router-dom";

const LINE_REF = /\bL(\d+)(?:–L(\d+))?\b/g;

/** Renders text, turning line references such as "L120" or "L303–L999" into links to the raw log explorer. */
export function LineRefText({ text, analysisId }: { text: string; analysisId: string }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(LINE_REF)) {
    const index = match.index ?? 0;
    if (index > last) parts.push(text.slice(last, index));
    parts.push(
      <Link
        key={`${index}-${match[0]}`}
        to={`/analyses/${analysisId}/logs?line=${match[1]}`}
        className="rounded bg-teal-50 px-1 font-mono text-[0.85em] font-semibold text-teal-800 hover:bg-teal-100 hover:underline"
        title={`Open line ${match[1]} in the raw log explorer`}
      >
        {match[0]}
      </Link>,
    );
    last = index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return <>{parts}</>;
}
