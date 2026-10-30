/** A plan ahead wait (ADR-0009), at most a week, in the largest whole units. */
export function formatWait(minutes: number): string {
  const days = Math.floor(minutes / (24 * 60));
  const hours = Math.floor((minutes % (24 * 60)) / 60);
  const rest = minutes % 60;
  const parts: string[] = [];
  if (days > 0) parts.push(`${String(days)} ${days === 1 ? "day" : "days"}`);
  if (hours > 0) parts.push(`${String(hours)} h`);
  // Minutes only matter under a day: "1 day 20 min" is false precision.
  if (rest > 0 && days === 0) parts.push(`${String(rest)} min`);
  return parts.join(" ");
}
