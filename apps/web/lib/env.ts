/**
 * The API origin, read once. **A pure read — this never throws.**
 *
 * #80: an *unset* `NEXT_PUBLIC_API_URL` takes the fallback below, but an
 * **empty** one does not — `""` is not `undefined`, so `API_BASE_URL` becomes
 * the empty string, every request goes to a same-origin relative path the
 * deployment does not serve, and the error degrades to "Could not reach the API
 * at ." Vercel lets you save an empty-string variable, so this is reachable.
 *
 * **The fix is `scripts/check-env.mjs`, run as `prebuild`, not a throw here.**
 * A module that throws at load fails the build only if it is evaluated during
 * prerender; if it is first evaluated in the browser the learner gets a blank
 * screen — a worse failure than #80 describes, landing on a phone instead of in
 * a build log. So the check is build-time and unconditional, and this file
 * stays a read.
 *
 * The `||` rather than `??` is deliberate now that the build refuses an empty
 * value: in development an empty variable means the same thing as an unset one.
 */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
