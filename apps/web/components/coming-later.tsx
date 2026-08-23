import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

/**
 * What will live on a page that has nothing on it yet, and which slice brings
 * it. A placeholder that says "coming soon" teaches the reader nothing; this
 * one is readable next to docs/TASKS-v3-web.md.
 */
export function ComingLater({
  slice,
  title,
  items,
}: {
  slice: string;
  title: string;
  items: string[];
}) {
  return (
    <Card className="border-dashed bg-card/60">
      <CardHeader className="gap-1">
        <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
          Arrives in {slice}
        </p>
        <CardTitle className="text-lg">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2 text-sm text-muted-foreground">
          {items.map((item) => (
            <li key={item} className="flex gap-2.5">
              <span
                className="mt-[0.45rem] h-1.5 w-1.5 shrink-0 rounded-full bg-primary/60"
                aria-hidden
              />
              <span className="leading-relaxed">{item}</span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
