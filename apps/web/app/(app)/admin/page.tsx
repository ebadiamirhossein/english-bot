import { AdminView } from "@/components/admin/admin-view";

/**
 * W23 — the operator's panel, the bot's `/admin` on the web. **Not linked from
 * the nav or the menu**: it is reached by typing `/admin`, as the bot's was by
 * typing the command, and a learner who does so reads one neutral line (the
 * API answers them 404). The header lives in the view, so a learner never sees
 * the word *Operator*.
 */
export default function AdminPage() {
  return <AdminView />;
}
