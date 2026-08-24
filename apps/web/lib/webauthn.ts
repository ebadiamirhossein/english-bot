/**
 * Passkey ceremonies in the browser.
 *
 * **There is deliberately no base64url encoder in this file.** Every field the
 * WebAuthn API takes and returns is binary, and the classic way to drive it is
 * to hand-convert a dozen of them. That code is silent when it is wrong: a
 * mangled challenge or credential id surfaces as `NotAllowedError`, which is
 * the same error the browser throws when the learner cancels — so a bug looks
 * exactly like someone changing their mind.
 *
 * Instead this uses the native JSON bridge:
 *   - `PublicKeyCredential.parseCreationOptionsFromJSON()`
 *   - `PublicKeyCredential.parseRequestOptionsFromJSON()`
 *   - `credential.toJSON()`
 *
 * which speak exactly the JSON shape py_webauthn emits and consumes, and is
 * available in Safari 17.4+ and Chrome 119+. Both learners' devices are past
 * those (an iPhone 17, and Android Chrome which updates independently of the
 * OS), and `passkeysSupported()` is what turns anything older into a clear
 * message rather than a mystery.
 */

import { ApiError, API_BASE_URL } from "@/lib/api";

/** Everything the ceremonies need, in one check. */
export function passkeysSupported(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.PublicKeyCredential !== "undefined" &&
    typeof PublicKeyCredential.parseCreationOptionsFromJSON === "function" &&
    typeof PublicKeyCredential.parseRequestOptionsFromJSON === "function"
  );
}

/**
 * True when the learner backed out (or the prompt timed out).
 *
 * Worth distinguishing because it is the one failure that is not a failure —
 * it gets a "try again when you're ready", never anything that reads as
 * blame (CLAUDE.md §4).
 */
export function wasCancelled(error: unknown): boolean {
  return error instanceof DOMException && error.name === "NotAllowedError";
}

type Json = Record<string, unknown>;

async function post<T>(path: string, body?: Json): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      // The session cookie lives on the API's own origin, so every call has to
      // opt in to sending it.
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body ?? {}),
    });
  } catch {
    throw new ApiError(
      `Could not reach the API at ${API_BASE_URL}. It may be down, or the ` +
        `origin may not be allowed.`,
    );
  }
  if (!response.ok) {
    throw new ApiError(`${path} returned ${response.status}`, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export type SessionUser = {
  user_id: number;
  name: string;
  expires_at: string;
};

/** First enrolment: the address the operator set, plus the code they handed over. */
export async function enrol(
  email: string,
  claimToken: string,
): Promise<SessionUser> {
  const optionsJson = await post<PublicKeyCredentialCreationOptionsJSON>(
    "/auth/register/begin",
    { email, claim_token: claimToken },
  );
  const credential = (await navigator.credentials.create({
    publicKey: PublicKeyCredential.parseCreationOptionsFromJSON(optionsJson),
  })) as PublicKeyCredential | null;
  if (!credential) throw new ApiError("No passkey was created.");

  return post<SessionUser>("/auth/register/finish", {
    credential: credential.toJSON(),
    claim_token: claimToken,
  });
}

/** Sign in. No identifier is typed — the passkey is discoverable. */
export async function signIn(): Promise<SessionUser> {
  const optionsJson = await post<PublicKeyCredentialRequestOptionsJSON>(
    "/auth/login/begin",
  );
  const assertion = (await navigator.credentials.get({
    publicKey: PublicKeyCredential.parseRequestOptionsFromJSON(optionsJson),
  })) as PublicKeyCredential | null;
  if (!assertion) throw new ApiError("No passkey was offered.");

  return post<SessionUser>("/auth/login/finish", {
    credential: assertion.toJSON(),
  });
}

/** Add this device to an account that is already enrolled. Needs a session. */
export async function addPasskey(): Promise<void> {
  const optionsJson = await post<PublicKeyCredentialCreationOptionsJSON>(
    "/auth/passkeys/begin",
  );
  const credential = (await navigator.credentials.create({
    publicKey: PublicKeyCredential.parseCreationOptionsFromJSON(optionsJson),
  })) as PublicKeyCredential | null;
  if (!credential) throw new ApiError("No passkey was created.");
  await post("/auth/passkeys/finish", { credential: credential.toJSON() });
}

export async function signOut(): Promise<void> {
  await post("/auth/logout");
}
