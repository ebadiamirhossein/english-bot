"use client";

/**
 * W23 — the operator's panel: the bot's `/admin` home screen, ported. TASKS'
 * row: *"`/admin` ported (activity never content)"*.
 *
 * **What it draws is the wire's, and the wire is activity only** — each
 * learner's name, level, streak, active days, last practised date, and whether
 * they are paused or revoked; and how many access requests wait. No sentence,
 * no correction, no topic can reach this screen because no field carries one
 * (`AdminUserOut`, held exactly by `tests/test_admin_route.py`).
 *
 * **READ-ONLY.** Approve, decline, revoke and pause stay on the bot until W22;
 * the requests line says so.
 *
 * **A learner who types `/admin` reads one neutral line** — the API answers
 * them 404 and this shows neither the header nor the word *Operator*.
 *
 * Conventions are `/progress`'s (ruling 0.3): the mono eyebrow, cards on
 * `bg-card`, the serif for names.
 */

import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/page-header";
import { ADMIN } from "@/components/session/copy";
import { Button } from "@/components/ui/button";
import { ApiError, getAdminActivity, type AdminActivity, type AdminUser } from "@/lib/api";

type Phase =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "problem" }
  | { kind: "ready"; activity: AdminActivity };

const EYEBROW =
  "font-mono text-[0.625rem] uppercase tracking-[0.11em] text-muted-foreground";
const CARD = "rounded-2xl border border-border bg-card p-4";

function shortDate(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
}

export function AdminView() {
  const [phase, setPhase] = useState<Phase>({ kind: "loading" });

  const load = useCallback(() => {
    setPhase({ kind: "loading" });
    getAdminActivity()
      .then((activity) => setPhase({ kind: "ready", activity }))
      .catch((error: unknown) =>
        setPhase(
          error instanceof ApiError && error.status === 404
            ? { kind: "not-found" }
            : { kind: "problem" },
        ),
      );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4" data-testid="admin-screen" data-phase={phase.kind}>
      {phase.kind === "not-found" ? (
        <p className="text-base leading-relaxed" data-testid="admin-not-found">
          {ADMIN.notFound}
        </p>
      ) : null}
      {phase.kind === "problem" ? (
        <>
          <Header />
          <div className="space-y-3" data-testid="admin-problem">
            <p className="text-base leading-relaxed">{ADMIN.trouble}</p>
            <Button type="button" className="min-h-11" onClick={load}>
              {ADMIN.retry}
            </Button>
          </div>
        </>
      ) : null}
      {phase.kind === "ready" ? (
        <>
          <Header />
          <Panel activity={phase.activity} />
        </>
      ) : null}
    </div>
  );
}

function Header() {
  return (
    <PageHeader eyebrow={ADMIN.eyebrow} title={ADMIN.title}>
      {ADMIN.subline}
    </PageHeader>
  );
}

function Panel({ activity }: { activity: AdminActivity }) {
  const { pending_requests, lookback_days, users } = activity;
  return (
    <>
      <p className="max-w-prose text-sm leading-relaxed" data-testid="admin-requests">
        {pending_requests > 0 ? ADMIN.requests(pending_requests) : ADMIN.requestsNone}
      </p>
      {users.length === 0 ? (
        <p className="text-base leading-relaxed" data-testid="admin-empty">
          {ADMIN.empty}
        </p>
      ) : (
        <ul className="space-y-3" data-testid="admin-users">
          {users.map((user) => (
            <LearnerCard key={user.id} user={user} lookback={lookback_days} />
          ))}
        </ul>
      )}
    </>
  );
}

function LearnerCard({ user, lookback }: { user: AdminUser; lookback: number }) {
  return (
    <li className={CARD} data-testid="admin-user" aria-labelledby={`admin-user-${user.id}`}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 id={`admin-user-${user.id}`} className="min-w-0 break-words font-heading text-xl">
          {user.name}
        </h2>
        <span className="flex flex-wrap gap-1.5">
          {user.paused ? <Tag>{ADMIN.paused}</Tag> : null}
          {user.revoked ? <Tag>{ADMIN.revoked}</Tag> : null}
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
        <Fact label={ADMIN.level} value={user.cefr_level} />
        <Fact label={ADMIN.streak} value={String(user.current_streak)} />
        <Fact label={ADMIN.active(lookback)} value={String(user.active_days)} />
        <Fact
          label={ADMIN.last}
          value={user.last_active ? shortDate(user.last_active) : ADMIN.never}
        />
      </dl>
    </li>
  );
}

function Fact({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className={EYEBROW}>{label}</dt>
      <dd className="mt-1 font-heading text-lg leading-none">{value}</dd>
    </div>
  );
}

function Tag({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="rounded-full border border-border px-2 py-0.5 text-xs text-muted-foreground"
      data-testid="admin-tag"
    >
      {children}
    </span>
  );
}
