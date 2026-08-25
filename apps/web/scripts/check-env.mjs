/**
 * Refuse a production build with no API origin. Known issue #80.
 *
 * Runs as `prebuild`, so `pnpm build` fails before Next starts rather than
 * shipping a bundle whose every request goes to a relative path the deployment
 * does not serve. The failure #80 describes is silent and reaches a learner's
 * phone as "Could not reach the API at ." — indistinguishable from the API
 * actually being down, which is the misdirection W2a shipped once already.
 *
 * Deliberately *not* a throw inside `lib/env.ts`: a module-load throw fails the
 * build only if that module is evaluated during prerender, and otherwise
 * white-screens the browser instead.
 *
 * Development is exempt: `pnpm dev` never runs this, and `lib/env.ts` falls back
 * to localhost there.
 */
const value = process.env.NEXT_PUBLIC_API_URL;

if (value === undefined || value.trim() === "") {
  console.error(
    "\nNEXT_PUBLIC_API_URL is missing or empty.\n\n" +
      "  Set it to the API origin (for example https://api.foundgrant.com)\n" +
      "  in the Vercel project settings, then redeploy.\n\n" +
      "  Refusing to build: an empty value produces a bundle that cannot reach\n" +
      "  the API, and the failure looks exactly like the API being down (#80).\n",
  );
  process.exit(1);
}

if (!/^https?:\/\//.test(value.trim())) {
  console.error(
    `\nNEXT_PUBLIC_API_URL is not scheme-qualified: ${value}\n\n` +
      "  It must start with http:// or https://, or every request resolves\n" +
      "  against the page origin instead of the API.\n",
  );
  process.exit(1);
}

console.log(`NEXT_PUBLIC_API_URL = ${value.trim()}`);
