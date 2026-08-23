import type { ReactNode } from "react";

export function PageHeader({
  eyebrow,
  title,
  children,
}: {
  eyebrow: string;
  title: string;
  children?: ReactNode;
}) {
  return (
    <header className="space-y-1.5">
      <p className="text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
        {eyebrow}
      </p>
      <h1 className="text-3xl leading-tight">{title}</h1>
      {children ? (
        <p className="max-w-prose text-sm leading-relaxed text-muted-foreground">
          {children}
        </p>
      ) : null}
    </header>
  );
}
